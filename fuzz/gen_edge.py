#!/usr/bin/env python3
"""Targeted adversarial edge cases for integer-overflow / oversize handling.

These are hand-structured (not random) so each exercises a specific boundary:
32-bit and 64-bit length overflow, declared size beyond the buffer, gigantic
channel/frame counts, and inconsistent header vs. payload lengths.
"""
import os
import struct
import sys


def wav(chunk_size, fmt_size=None, channels=None, extra=b""):
    # RIFF header with attacker-controlled outer size; 'data' length field is
    # also set to the same huge value while the backing buffer stays tiny.
    riff = b"RIFF" + struct.pack("<I", chunk_size & 0xFFFFFFFF) + b"WAVE"
    fmt = b"fmt " + struct.pack("<I", 16)
    body = struct.pack("<HHIIHH", 1, channels or 2, 48000, 192000, 4, 16)
    data = b"data" + struct.pack("<I", chunk_size & 0xFFFFFFFF)
    return riff + fmt + body + data + extra


def w64_guid_len(length64):
    # W64 uses 16-byte GUIDs followed by a 64-bit chunk size.
    riff_guid = bytes.fromhex("666669722e91cf11a5d628db04c10000")
    wave_guid = bytes.fromhex("6d616e722f91cf11a5d628db04c10000")
    data_guid = bytes.fromhex("646174612f91cf11a5d628db04c10000")
    out = riff_guid + struct.pack("<Q", length64) + wave_guid
    out += data_guid + struct.pack("<Q", length64)
    return out


def main():
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    cases = {}

    # 32-bit boundary values in RIFF/data length fields.
    for val in (0xFFFFFFFF, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFE,
                0x40000000, 0x01000000):
        cases[f"wav_len_{val:#010x}.bin"] = wav(val)

    # 64-bit overflow attempts in W64 chunk sizes.
    for val in (0xFFFFFFFFFFFFFFFF, 0x8000000000000000,
                0x7FFFFFFFFFFFFFFF, 0xFFFFFFFF00000000,
                0x0000000100000000):
        cases[f"w64_len_{val:#018x}.bin"] = w64_guid_len(val)

    # Gigantic channel counts in a WAV fmt body.
    for ch in (0xFFFF, 0x7FFF, 0x10000, 0x7FFFFFFF):
        riff = b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + b"WAVE"
        fmt = b"fmt " + struct.pack("<I", 16)
        body = struct.pack("<HHIIHH", 1, ch & 0xFFFF, 48000,
                           0xFFFFFFFF, 4, 16)
        cases[f"wav_channels_{ch:#x}.bin"] = riff + fmt + body

    # Declared fmt chunk huge but almost no bytes follow.
    riff = b"RIFF" + struct.pack("<I", 64) + b"WAVE"
    cases["wav_huge_fmt_truncated.bin"] = (
        riff + b"fmt " + struct.pack("<I", 0x7FFFFFFF) + b"\x01\x00")

    # Outer RIFF says tiny but data chunk says enormous.
    cases["wav_inconsistent_sizes.bin"] = (
        b"RIFF" + struct.pack("<I", 12) + b"WAVE" +
        b"data" + struct.pack("<I", 0xFFFFFFFF) + b"\x00\x00")

    # Length field overflow when adding a header offset (size = -16).
    cases["wav_negative_relative.bin"] = wav(0xFFFFFFF0)

    # Empty / near-empty magic only.
    cases["magic_riff_only.bin"] = b"RIFF"
    cases["magic_riff_size.bin"] = b"RIFF" + struct.pack("<I", 0xFFFFFFFF)

    # AIFF FORM with absurd COMM size.
    form = b"FORM" + struct.pack(">I", 0x7FFFFFFF) + b"AIFF"
    cases["aiff_huge_comm.bin"] = (
        form + b"COMM" + struct.pack(">I", 0x7FFFFFFF) + b"\x00\x02")

    # CAF with 64-bit huge data size.
    caf = b"caff" + struct.pack(">HH", 1, 0)
    cases["caf_huge_data.bin"] = (
        caf + b"desc" + struct.pack(">Q", 0xFFFFFFFFFFFFFFFF) +
        b"data" + struct.pack(">Q", 0xFFFFFFFFFFFFFFFF))

    for name, blob in cases.items():
        with open(os.path.join(outdir, name), "wb") as fh:
            fh.write(blob)
    print(f"wrote {len(cases)} targeted edge cases to {outdir}")


if __name__ == "__main__":
    main()
