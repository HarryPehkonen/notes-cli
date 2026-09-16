#!/usr/bin/env sh
# The gate: what must pass before a commit. No network, no dependencies.
set -eu
cd "$(dirname "$0")"

echo "== syntax =="
python3 -m py_compile hn
echo "   hn compiles"

echo "== unit tests =="
# No pipe here: a pipeline would return tail's status, not the tests'.
# A gate that cannot fail is not a gate.
out=$(mktemp)
if ! python3 -m unittest discover -s tests >"$out" 2>&1; then
  tail -25 "$out"
  rm -f "$out"
  echo "GATE FAILED"
  exit 1
fi
tail -3 "$out"
rm -f "$out"

echo "== CLI smoke =="
./hn --help >/dev/null
echo "   hn --help ok"

echo "GATE PASSED"
