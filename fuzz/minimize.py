#!/usr/bin/env python3
"""Minimise a malformed input while preserving its failure signature.

The signature is (status, error-string) reported by the (fast) reference
harness. Strategy:
  1. block-removal delta debugging with shrinking block size,
  2. single-byte removal sweep,
  3. byte-value shrinking toward 0 while keeping the signature.

Re-checks against the ASan harness at the end so every minimised counterexample
is still rejected cleanly (no crash / OOB / leak) there as well.
"""
import json
import os
import subprocess
import sys
import tempfile


_TMPDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "minis", "tmp")


def signature(harness, data):
    os.makedirs(_TMPDIR, exist_ok=True)
    fd, path = tempfile.mkstemp(dir=_TMPDIR, suffix=".bin")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        proc = subprocess.run([harness, path], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=30)
    finally:
        os.remove(path)
    out = proc.stdout.decode("utf-8", "replace").strip()
    if not out.startswith("{"):
        return None, proc.returncode
    parsed = json.loads(out)
    return (parsed["status"], parsed["error"]), proc.returncode


def block_dd(harness, data, target_sig):
    cur = bytearray(data)
    block = max(1, len(cur) // 2)
    while block >= 1 and len(cur) > 1:
        progressed = False
        i = 0
        while i + block <= len(cur):
            trial = cur[:i] + cur[i + block:]
            if not trial:
                i += block
                continue
            sig, rc = signature(harness, bytes(trial))
            if rc == 0 and sig == target_sig:
                cur = trial
                progressed = True
                # do not advance i; re-test same index after shrink
            else:
                i += block
        if not progressed:
            block //= 2
    return bytes(cur)


def byte_remove(harness, data, target_sig):
    cur = bytearray(data)
    i = 0
    while i < len(cur) and len(cur) > 1:
        trial = cur[:i] + cur[i + 1:]
        sig, rc = signature(harness, bytes(trial))
        if rc == 0 and sig == target_sig:
            cur = trial
        else:
            i += 1
    return bytes(cur)


def byte_shrink(harness, data, target_sig):
    cur = bytearray(data)
    for i in range(len(cur)):
        original = cur[i]
        for cand in (0, 1, 0x7F, 0xFF, original >> 1):
            if cand == original:
                continue
            cur[i] = cand
            sig, rc = signature(harness, bytes(cur))
            if rc == 0 and sig == target_sig:
                original = cand
            else:
                cur[i] = original
    return bytes(cur)


def main():
    ref_h, asan_h, in_path, out_path = sys.argv[1:5]
    data = open(in_path, "rb").read()
    target_sig, rc = signature(ref_h, data)
    if target_sig is None or target_sig[0] == "ok":
        print("input is not a failing case; nothing to minimise")
        return 1

    print(f"start: {len(data)} bytes sig={target_sig}")
    cur = block_dd(ref_h, data, target_sig)
    cur = byte_remove(ref_h, cur, target_sig)
    cur = byte_shrink(ref_h, cur, target_sig)
    # second removal pass after value shrinking often unlocks more deletions
    cur = byte_remove(ref_h, cur, target_sig)

    # Verify on the sanitizer build: same signature, clean exit.
    asan_sig, asan_rc = signature(asan_h, cur)
    clean = asan_rc == 0 and asan_sig == target_sig

    with open(out_path, "wb") as fh:
        fh.write(cur)

    print(f"end:   {len(cur)} bytes (from {len(data)})")
    print(f"signature preserved: {asan_sig == target_sig}; "
          f"asan clean exit: {asan_rc == 0}")
    print(f"hex: {cur.hex()}")
    meta = {"source": in_path, "output": out_path,
            "original_size": len(data), "minimized_size": len(cur),
            "signature": list(target_sig), "asan_clean": clean,
            "hex": cur.hex()}
    with open(out_path + ".json", "w") as fh:
        json.dump(meta, fh, indent=1)
    return 0 if clean else 2


if __name__ == "__main__":
    sys.exit(main())
