#!/usr/bin/env sh
# The gate: what must pass before a commit. No network, no dependencies.
set -eu
cd "$(dirname "$0")"

echo "== syntax =="
python3 -m py_compile hn
echo "   hn compiles"

echo "== unit tests =="
python3 -m unittest discover -s tests 2>&1 | tail -3

echo "== CLI smoke =="
./hn --help >/dev/null
echo "   hn --help ok"

echo "GATE PASSED"
