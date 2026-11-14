#!/usr/bin/env python3
"""Run the malformed corpus under the ASan/UBSan/LSan harness, one process
per input, and aggregate results.

For every file we record:
  - class      : mutation class from the filename
  - status     : ok / open_error / read_error from the harness JSON
  - error      : libsndfile error string
  - max_access : highest byte offset the reader touched (failure offset)
  - size       : file size
  - crash      : nonzero exit / sanitizer signal

A sanitizer (ASan heap/stack OOB, UBSan, LSan leak, abort) makes the process
exit non-zero or print a runtime error; both are detected here.
"""
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed


SAN_ENV = dict(os.environ)
SAN_ENV.update({
    "ASAN_OPTIONS": "detect_leaks=1:abort_on_error=1:halt_on_error=1:"
                     "exitcode=99:symbolize=1:allocator_may_return_null=1",
    "UBSAN_OPTIONS": "halt_on_error=1:exitcode=98:print_stacktrace=1",
    "LSAN_OPTIONS": "exitcode=97",
})


def classify(path):
    base = os.path.basename(path)
    parts = base.split("_")
    return parts[2] if len(parts) > 2 else "unknown"


def run_one(args):
    harness, path = args
    try:
        proc = subprocess.run(
            [harness, path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=SAN_ENV,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {"file": path, "class": classify(path), "crash": True,
                "kind": "timeout", "stderr": "timeout after 30s",
                "status": "timeout", "error": "timeout",
                "max_access": -1, "size": os.path.getsize(path)}

    out = proc.stdout.decode("utf-8", "replace").strip()
    err = proc.stderr.decode("utf-8", "replace")
    record = {"file": path, "class": classify(path),
              "exit": proc.returncode, "stderr": err[:4000]}
    parsed = None
    if out.startswith("{"):
        try:
            parsed = json.loads(out)
        except json.JSONDecodeError:
            parsed = None
    if parsed:
        record.update({
            "status": parsed.get("status"),
            "error": parsed.get("error"),
            "max_access": parsed.get("max_access"),
            "size": parsed.get("size"),
        })
    else:
        record.update({"status": "no_json", "error": out[:200],
                       "max_access": -1,
                       "size": os.path.getsize(path)})

    sanitizer = ("AddressSanitizer" in err or "runtime error" in err
                 or "LeakSanitizer" in err or "SUMMARY:" in err)
    record["crash"] = proc.returncode != 0 or sanitizer or record["status"] == "no_json"
    if sanitizer:
        record["kind"] = "sanitizer"
    elif proc.returncode != 0:
        record["kind"] = f"exit_{proc.returncode}"
    elif record["status"] == "no_json":
        record["kind"] = "no_json"
    else:
        record["kind"] = "clean"
    return record


def main():
    harness = sys.argv[1]
    corpus = sys.argv[2]
    report_json = sys.argv[3]
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 8

    paths = sorted(os.path.join(corpus, p) for p in os.listdir(corpus))
    records = []
    crashes = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_one, (harness, p)) for p in paths]
        for i, fut in enumerate(as_completed(futures), 1):
            rec = fut.result()
            records.append(rec)
            if rec["crash"]:
                crashes.append(rec)
            if i % 500 == 0:
                print(f"  processed {i}/{len(paths)}, crashes so far {len(crashes)}")

    with tempfile.NamedTemporaryFile("w", delete=False,
                                     suffix=".json", dir=os.path.dirname(report_json) or ".") as tmp:
        json.dump(records, tmp, indent=1)
        tmp_name = tmp.name
    os.replace(tmp_name, report_json)

    total = len(records)
    by_class = {}
    by_status = {}
    for rec in records:
        c = rec["class"]
        by_class.setdefault(c, {"total": 0, "crash": 0})
        by_class[c]["total"] += 1
        if rec["crash"]:
            by_class[c]["crash"] += 1
        s = rec["status"]
        by_status[s] = by_status.get(s, 0) + 1

    print(f"\nTOTAL={total} CRASHES={len(crashes)}")
    print("by status:", json.dumps(by_status, sort_keys=True))
    print("by class :", json.dumps(by_class, sort_keys=True))
    if crashes:
        print("\nFIRST CRASHES:")
        for rec in crashes[:10]:
            print(" ", rec["file"], rec["kind"], rec.get("error"))
    return 1 if crashes else 0


if __name__ == "__main__":
    sys.exit(main())
