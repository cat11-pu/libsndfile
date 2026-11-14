#!/usr/bin/env python3
"""Cross-build equivalence check on the VALID corpus.

For every valid file, decode it with both the ASan build and the clean
reference build. Compare:
  1. the textual SF_INFO header (format, subtype, frames, rate, channels),
  2. every decoded float32 sample (byte-for-byte),
  3. the trailer (frames actually read, sf_error, max_access).

The ASan build also runs with leak detection enabled, so this doubles as the
leak/no-crash check over all well-formed inputs.
"""
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed


ENV = dict(os.environ)
ENV.update({
    "ASAN_OPTIONS": "detect_leaks=1:abort_on_error=1:halt_on_error=1:exitcode=99",
    "UBSAN_OPTIONS": "halt_on_error=1:exitcode=98",
    "LSAN_OPTIONS": "exitcode=97",
})


def split_output(blob: bytes):
    # Header is the first line; trailer the last line; everything between is
    # the raw float payload.
    first_nl = blob.find(b"\n")
    last_nl = blob.rfind(b"\n")
    header = blob[:first_nl]
    trailer = blob[last_nl + 1:]
    payload = blob[first_nl + 1:last_nl]
    return header, payload, trailer


def compare_one(args):
    asan_h, ref_h, path = args
    result = {"file": path, "match": False, "reason": None,
              "asan_exit": None, "ref_exit": None, "samples": 0}
    try:
        a = subprocess.run([asan_h, path], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, env=ENV, timeout=30)
        r = subprocess.run([ref_h, path], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=30)
    except subprocess.TimeoutExpired:
        result["reason"] = "timeout"
        return result

    result["asan_exit"] = a.returncode
    result["ref_exit"] = r.returncode

    if a.returncode != 0:
        result["reason"] = "asan_crash_or_leak"
        result["stderr"] = a.stderr.decode("utf-8", "replace")[:2000]
        return result

    ah, ap, at = split_output(a.stdout)
    rh, rp, rt = split_output(r.stdout)
    result["samples"] = len(ap) // 4

    if ah != rh:
        result["reason"] = "header_diff"
        result["asan_header"] = ah.decode("utf-8", "replace")
        result["ref_header"] = rh.decode("utf-8", "replace")
        return result
    if ap != rp:
        # Locate the first differing sample for a precise report.
        n = min(len(ap), len(rp))
        idx = next((i for i in range(n) if ap[i] != rp[i]), n)
        result["reason"] = "sample_diff"
        result["first_diff_byte"] = idx
        result["asan_len"] = len(ap)
        result["ref_len"] = len(rp)
        return result
    if at != rt:
        result["reason"] = "trailer_diff"
        result["asan_trailer"] = at.decode("utf-8", "replace")
        result["ref_trailer"] = rt.decode("utf-8", "replace")
        return result

    result["match"] = True
    return result


def main():
    asan_h, ref_h, corpus, report_json = sys.argv[1:5]
    workers = int(sys.argv[5]) if len(sys.argv) > 5 else 8
    paths = sorted(os.path.join(corpus, p) for p in os.listdir(corpus))

    results = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(compare_one, (asan_h, ref_h, p)) for p in paths]
        for i, fut in enumerate(as_completed(futures), 1):
            results.append(fut.result())
            if i % 100 == 0:
                ok = sum(1 for x in results if x["match"])
                print(f"  {i}/{len(paths)} compared, matching {ok}")

    with open(report_json, "w") as fh:
        json.dump(results, fh, indent=1)

    total = len(results)
    matched = sum(1 for x in results if x["match"])
    total_samples = sum(x["samples"] for x in results)
    fails = [x for x in results if not x["match"]]
    reasons = {}
    for x in fails:
        reasons[x["reason"]] = reasons.get(x["reason"], 0) + 1

    print(f"\nTOTAL={total} MATCH={matched} MISMATCH={len(fails)}")
    print(f"TOTAL_FLOAT_SAMPLES_COMPARED={total_samples}")
    if reasons:
        print("failure reasons:", json.dumps(reasons, sort_keys=True))
        for x in fails[:10]:
            print(" ", x["file"], x["reason"])
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
