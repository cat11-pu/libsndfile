#!/usr/bin/env python3
"""Generate ~3000 *malformed* audio files from the valid seed corpus.

Mutation classes (each output filename is prefixed with the class so the
report can attribute results):
  trunc   - truncation at various offsets (header, mid-chunk, single byte)
  field   - header/field corruption: zeroed, misaligned, swapped, huge values
  size    - declared sizes/lengths/counts set to absurd/overflowing values
  enc     - illegal encodings / format subtype & endian / invalid magic
  bit     - single & multi bit/byte flips, insertion, deletion, duplication
  chaos   - heavy random mutation and entirely synthetic garbage

Everything is deterministic (fixed RNG seed) for reproducible minimisation.
"""
import os
import random
import struct
import sys

RNG = random.Random(0xC0FFEE)


def load_seeds(seed_dir, cap=120):
    files = []
    names = sorted(os.listdir(seed_dir))
    # Spread across formats rather than taking only the alphabetical prefix.
    step = max(1, len(names) // cap)
    for name in names[::step][:cap]:
        with open(os.path.join(seed_dir, name), "rb") as fh:
            files.append((name, bytearray(fh.read())))
    return files


def truncations(data):
    out = []
    n = len(data)
    if n == 0:
        return out
    points = {0, 1, 2, 3, 4, 7, 8, 11, 12, 15, 16, n // 4, n // 2,
              (3 * n) // 4, n - 1, max(0, n - 2), max(0, n - 4),
              max(0, n - 8), max(0, n - 16)}
    for _ in range(6):
        points.add(RNG.randrange(n))
    for p in sorted(p for p in points if 0 <= p <= n):
        out.append((f"trunc_at{p}", bytes(data[:p])))
    return out


def field_corruption(data):
    out = []
    n = len(data)
    if n < 4:
        return out

    # Zero a header region / single field at several early offsets.
    early = [p for p in (0, 4, 8, 12, 16, 20, 24, 28) if p + 4 <= n]
    for p in early:
        d = bytearray(data)
        d[p:p + 4] = b"\x00\x00\x00\x00"
        out.append((f"field_zero@{p}", bytes(d)))

    # Write huge 32-bit values into length/size/channel-like fields.
    huge_vals = (0xFFFFFFFF, 0x7FFFFFFF, 0x80000000, 0x40000000,
                 0x00FFFFFF, 0x01000000)
    positions = [p for p in range(4, min(n - 4, 64), 4)]
    for i, p in enumerate(positions[:8]):
        for endian in ("<", ">"):
            d = bytearray(data)
            d[p:p + 4] = struct.pack(endian + "I", huge_vals[i % len(huge_vals)])
            out.append((f"size_huge{'BE' if endian == '>' else 'LE'}@{p}",
                        bytes(d)))

    # Channel/sample-rate style fields: zero and extreme.
    for p in positions[:6]:
        for val in (0, 1, 0xFFFF, 0x7FFFFFFF):
            d = bytearray(data)
            d[p:p + 4] = struct.pack("<I", val)
            out.append((f"field_val{val}@{p}", bytes(d)))

    # Swap adjacent 4-byte fields (header misalignment).
    for p in positions[:5]:
        if p + 8 <= n:
            d = bytearray(data)
            d[p:p + 4], d[p + 4:p + 8] = bytes(d[p + 4:p + 8]), bytes(d[p:p + 4])
            out.append((f"field_swap@{p}", bytes(d)))

    # Endian inversion of a chunk-size field region.
    if n >= 12:
        d = bytearray(data)
        chunk = bytes(d[4:8])
        d[4:8] = chunk[::-1]
        out.append(("field_endian_swap4", bytes(d)))
    return out


def encoding_corruption(data):
    out = []
    n = len(data)
    if n < 12:
        return out

    # Replace format/subtype identifiers with reserved/invalid codes.
    invalid_codes = (0, 0xFFFF, 0x0000, 0x0099, 0x00FF, 0x7FFF, 0x1234)
    for p in range(8, min(n - 2, 40), 2):
        code = invalid_codes[(p // 2) % len(invalid_codes)]
        d = bytearray(data)
        d[p:p + 2] = struct.pack("<H", code)
        out.append((f"enc_code{code}@{p}", bytes(d)))

    # Invalid magic / container tags.
    magics = (b"\x00\x00\x00\x00", b"RIXX", b"ffff", b"\xff\xff\xff\xff",
              b"FORM", b"XXXX", b"OggS"[::-1])
    for i, magic in enumerate(magics):
        d = bytearray(data)
        d[0:4] = magic
        out.append((f"enc_magic{i}", bytes(d)))

    # WAVE/form-type tag mangling at offset 8.
    for tag in (b"\x00\x00\x00\x00", b"wavx", b"!!!!", b"\xff" * 4):
        d = bytearray(data)
        d[8:12] = tag
        out.append((f"enc_formtag", bytes(d)))
    return out


def bit_mutation(data):
    out = []
    n = len(data)
    if n == 0:
        return out

    # Single bit flips concentrated in headers plus some in the body.
    for _ in range(10):
        d = bytearray(data)
        pos = RNG.randrange(n)
        bit = RNG.randrange(8)
        d[pos] ^= (1 << bit)
        out.append((f"bit_flip@{pos}.b{bit}", bytes(d)))

    # Single byte overwrite.
    for _ in range(6):
        d = bytearray(data)
        pos = RNG.randrange(n)
        d[pos] = RNG.choice((0, 0xFF, 0x80, 0x7F, RNG.randrange(256)))
        out.append((f"byte_set@{pos}", bytes(d)))

    # Byte insertion / deletion / duplication.
    if n > 4:
        pos = RNG.randrange(min(n, 64))
        d = bytearray(data)
        d.insert(pos, RNG.randrange(256))
        out.append((f"byte_insert@{pos}", bytes(d)))

        d = bytearray(data)
        del d[pos]
        out.append((f"byte_delete@{pos}", bytes(d)))

        d = bytearray(data)
        d[pos:pos] = data[pos:pos + 1]
        out.append((f"byte_dup@{pos}", bytes(d)))

    # Chunk length extension without backing data.
    if n >= 8:
        d = bytearray(data)
        d[4:8] = struct.pack("<I", 0x7FFFFFFF)
        out.append(("size_extend_chunk", bytes(d)))
    return out


def chaos(data):
    out = []
    n = len(data)
    if n == 0:
        return out

    # Multi-bit burst corruption.
    d = bytearray(data)
    for _ in range(max(1, n // 16)):
        pos = RNG.randrange(n)
        d[pos] ^= RNG.randrange(1, 256)
    out.append(("chaos_burst", bytes(d)))

    # Reorder a header window.
    if n >= 16:
        d = bytearray(data)
        window = d[0:16]
        RNG.shuffle(window)
        d[0:16] = window
        out.append(("chaos_header_shuffle", bytes(d)))

    # Truncated then garbage appended.
    cut = max(1, n // 2)
    d = bytearray(data[:cut])
    d += bytes(RNG.randrange(256) for _ in range(RNG.randrange(1, 33)))
    out.append(("chaos_trash_append", bytes(d)))

    # All-zero and all-0xff buffers of varied length.
    out.append(("chaos_zeros", b"\x00" * RNG.randrange(1, 257)))
    out.append(("chaos_ffs", b"\xff" * RNG.randrange(1, 257)))

    # Pure synthetic garbage with an occasional magic prefix.
    garbage = bytes(RNG.randrange(256) for _ in range(RNG.randrange(1, 512)))
    out.append(("chaos_random", garbage))
    for prefix in (b"RIFF", b"FORM", b"fLaC", b"OggS", b"caff"):
        body = bytes(RNG.randrange(256) for _ in range(RNG.randrange(0, 128)))
        out.append(("chaos_magic_garbage", prefix + body))
    return out


MUTATORS = [truncations, field_corruption, encoding_corruption,
            bit_mutation, chaos]


def main():
    seed_dir = sys.argv[1]
    out_dir = sys.argv[2]
    target = int(sys.argv[3]) if len(sys.argv) > 3 else 3000
    os.makedirs(out_dir, exist_ok=True)

    seeds = load_seeds(seed_dir)
    written = 0
    si = 0
    seen = set()
    while written < target:
        name, data = seeds[si % len(seeds)]
        si += 1
        mutator = MUTATORS[si % len(MUTATORS)]
        for label, blob in mutator(data):
            if written >= target:
                break
            key = blob
            if key in seen:
                continue
            seen.add(key)
            cls = label.split("_", 1)[0]
            fname = f"m_{written:05d}_{cls}_{label}.bin"
            with open(os.path.join(out_dir, fname), "wb") as fh:
                fh.write(blob)
            written += 1

    print(f"wrote {written} malformed files to {out_dir} from {len(seeds)} seeds")


if __name__ == "__main__":
    main()
