#!/usr/bin/env bash
# Build the four test harness binaries against the two libsndfile builds.
# Prereq: build-asan (ASan/UBSan static lib) and build-ref (Release static lib).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FUZZ="$ROOT/fuzz"
LIBS="-lm -lpthread -ldl"

gcc -g -O1 -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I"$ROOT/include" -I"$ROOT/build-asan" \
    "$FUZZ/harness_malformed.c" "$ROOT/build-asan/libsndfile.a" $LIBS \
    -o "$FUZZ/malformed_asan"

gcc -g -O1 -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I"$ROOT/include" -I"$ROOT/build-asan" \
    "$FUZZ/harness_decode.c" "$ROOT/build-asan/libsndfile.a" $LIBS \
    -o "$FUZZ/decode_asan"

gcc -O2 -I"$ROOT/include" -I"$ROOT/build-ref" \
    "$FUZZ/harness_malformed.c" "$ROOT/build-ref/libsndfile.a" $LIBS \
    -o "$FUZZ/malformed_ref"

gcc -O2 -I"$ROOT/include" -I"$ROOT/build-ref" \
    "$FUZZ/harness_decode.c" "$ROOT/build-ref/libsndfile.a" $LIBS \
    -o "$FUZZ/decode_ref"

echo "built: malformed_asan decode_asan malformed_ref decode_ref"
