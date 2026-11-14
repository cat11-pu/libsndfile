#!/usr/bin/env python3
"""Pick one representative malformed file per error signature and minimise
each into a smallest-possible counterexample, producing a curated corpus."""
import json
import os
import subprocess
import sys


def slug(text):
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " .'":
            out.append("_")
    s = "".join(out).strip("_")
    while "__" in s:
        s = s.replace("__", "_")
    return s[:48]


def main():
    ref_h, asan_h, report_json, outdir = sys.argv[1:5]
    os.makedirs(outdir, exist_ok=True)
    records = json.load(open(report_json))

    # One representative per (status,error); prefer smaller source files so
    # minimisation converges quickly.
    best = {}
    for rec in records:
        if rec["status"] == "ok":
            continue
        key = (rec["status"], rec["error"])
        size = rec["size"]
        if key not in best or size < best[key][0]:
            best[key] = (size, rec["file"])

    # Keep the most informative/common signatures, cap the curated set.
    ordered = sorted(best.items(), key=lambda kv: kv[1][0])
    cap = int(sys.argv[5]) if len(sys.argv) > 5 else 14
    ordered = ordered[:cap]

    summary = []
    for i, ((status, error), (size, path)) in enumerate(ordered):
        name = f"{i:02d}_{slug(error)}.bin"
        out_path = os.path.join(outdir, name)
        proc = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__),
                                          "minimize.py"),
             ref_h, asan_h, path, out_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True)
        tail = [ln for ln in proc.stdout.splitlines() if ln.startswith(("start", "end", "signature", "hex"))]
        meta = json.load(open(out_path + ".json"))
        summary.append({"name": name, "source": os.path.basename(path),
                        "status": status, "error": error,
                        "original_size": meta["original_size"],
                        "minimized_size": meta["minimized_size"],
                        "asan_clean": meta["asan_clean"], "hex": meta["hex"]})
        print(f"[{i+1}/{len(ordered)}] {name}: {meta['original_size']} -> "
              f"{meta['minimized_size']} B  ({error})")

    with open(os.path.join(outdir, "counterexamples.json"), "w") as fh:
        json.dump(summary, fh, indent=1)
    print(f"\nwrote {len(summary)} minimised counterexamples to {outdir}")


if __name__ == "__main__":
    main()
