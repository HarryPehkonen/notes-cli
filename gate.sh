#!/usr/bin/env sh
# The gate: what must pass before a commit. No network, no dependencies.
set -eu
cd "$(dirname "$0")"

echo "== syntax =="
python3 -m py_compile notes
echo "   notes compiles"

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

echo "== man page =="
if command -v scdoc >/dev/null 2>&1; then
  # scdoc's grammar is unforgiving: a tab-indented continuation line is read as a
  # table cell and the build fails. A man page that cannot be built is a man page
  # that ships wrong. Skipped where scdoc is missing - only packaging needs it.
  scdoc < man/notes.1.scd > /dev/null
  echo "   notes.1.scd builds"
else
  echo "   scdoc not installed - skipped"
fi

echo "== CLI smoke =="
./notes --help >/dev/null
echo "   notes --help ok"

echo "GATE PASSED"
