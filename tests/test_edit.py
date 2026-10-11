#!/usr/bin/env python3
"""Tests for hn edit — the write path. Offline: the API is faked.

The theme: whatever goes wrong, the user's text must survive and the server must not
be written. Every test below asserts "no PUT happened" somewhere.
"""

import importlib.machinery
import importlib.util
import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
# test_hn lives beside us and is importable under `discover -s tests`
import test_hn  # noqa: E402
from test_hn import NOTE_PINNED, FakeClient, run  # noqa: E402

notes = test_hn.notes


class EditClient(FakeClient):
    """Records writes; can serve a note that changes underneath us, or answer 409."""

    def __init__(self, note=None, change_between_reads=False, put_409=False):
        super().__init__()
        self.note = dict(note or NOTE_PINNED)
        self.change_between_reads = change_between_reads
        self.put_409 = put_409
        self.gets = 0
        self.puts = []

    def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        if path.startswith("/notes/") and path != "/notes":
            self.gets += 1
            if self.change_between_reads and self.gets >= 2:
                n = dict(self.note)
                n["updated_at"] = "2026-09-16T23:59:59.000Z"   # moved underneath
                n["content"] = "someone else's newer text\n"
                return n
            return self.note
        return super().get(path, params)

    def request(self, method, path, params=None, body=None):
        self.calls.append((method, path, params))
        if method == "PUT":
            self.puts.append(body)
            if self.put_409:
                raise notes.HnError("HTTP 409: Conflict", status=409)
            return {"id": self.note["id"], "updated_at": "2026-09-16T20:00:00.000Z"}
        return self.get(path, params)


def make_editor(tmp, script_body):
    """A fake editor: $1 is the file hn hands us."""
    p = Path(tmp) / "editor.sh"
    p.write_text("#!/bin/sh\n" + script_body + "\n")
    os.chmod(p, 0o755)
    return str(p)


class EditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # Scope TMPDIR to this test, so "what did we leave behind" is a question
        # about THIS run and not about earlier ones.
        self.tmpdir = tempfile.mkdtemp(prefix="hn-test-tmp-")
        self._old_tmpdir = os.environ.get("TMPDIR")
        os.environ["TMPDIR"] = self.tmpdir
        tempfile.tempdir = None   # tempfile caches its dir; force it to re-read TMPDIR

    def tearDown(self):
        tempfile.tempdir = None
        if self._old_tmpdir is None:
            os.environ.pop("TMPDIR", None)
        else:
            os.environ["TMPDIR"] = self._old_tmpdir

    def leftovers(self):
        return sorted(p.name for p in Path(self.tmpdir).glob("hn-edit-*"))

    def test_unchanged_note_sends_nothing(self):
        c = EditClient()
        rc, out, _ = run(["edit", "47", "--editor", make_editor(self.tmp, ":")], c)
        self.assertEqual(rc, 0)
        self.assertEqual(c.puts, [])
        self.assertIn("unchanged", out)

    def test_changed_note_sends_content_and_the_lock(self):
        c = EditClient()
        ed = make_editor(self.tmp, 'echo "added line" >> "$1"')
        rc, out, _ = run(["edit", "47", "--editor", ed], c)
        self.assertEqual(rc, 0)
        self.assertEqual(len(c.puts), 1)
        body = c.puts[0]
        # the content is what the editor wrote, and the lock is the value we read
        self.assertIn("added line", body["content"])
        self.assertIn("- water", body["content"])
        self.assertEqual(body["updated_at"], NOTE_PINNED["updated_at"])
        self.assertIn("updated", out)

    def test_editor_failure_writes_nothing(self):
        c = EditClient()
        ed = make_editor(self.tmp, 'echo "half a thought" >> "$1"; exit 3')
        with self.assertRaises(notes.HnError) as cm:
            run(["edit", "47", "--editor", ed], c)
        self.assertIn("exited 3", str(cm.exception))
        self.assertEqual(c.puts, [])

    def test_editor_removing_the_file_writes_nothing(self):
        c = EditClient()
        ed = make_editor(self.tmp, 'rm -f "$1"')
        with self.assertRaises(notes.HnError) as cm:
            run(["edit", "47", "--editor", ed], c)
        self.assertIn("nothing was written", str(cm.exception))
        self.assertEqual(c.puts, [])

    def test_conflict_refuses_and_keeps_the_text(self):
        """The note moved between our read and our write: refuse, keep the edit."""
        c = EditClient(change_between_reads=True)
        ed = make_editor(self.tmp, 'echo "my precious edit" >> "$1"')
        with self.assertRaises(notes.HnError) as cm:
            run(["edit", "47", "--editor", ed], c)
        msg = str(cm.exception)
        self.assertIn("changed on the server", msg)
        self.assertIn("NOTHING was written", msg)
        self.assertEqual(c.puts, [])
        # the edited file must still exist, and be findable from the message
        kept = [line for line in msg.splitlines() if "your edits:" in line]
        self.assertEqual(len(kept), 1, msg)
        path = Path(kept[0].split("your edits:")[1].split("(")[0].strip())
        self.assertTrue(path.exists())
        self.assertIn("my precious edit", path.read_text())
        # and the kept file is the only thing left behind
        self.assertEqual(len(self.leftovers()), 1,
                         "exactly the edited file should survive a conflict")

    def test_server_409_is_also_refused(self):
        c = EditClient(put_409=True)
        ed = make_editor(self.tmp, 'echo "x" >> "$1"')
        with self.assertRaises(notes.HnError) as cm:
            run(["edit", "47", "--editor", ed], c)
        self.assertIn("changed on the server", str(cm.exception))
        self.assertEqual(len(c.puts), 1)          # it tried
        self.assertEqual(c.puts[0]["updated_at"], NOTE_PINNED["updated_at"])

    def test_dry_run_sends_nothing(self):
        c = EditClient()
        ed = make_editor(self.tmp, 'echo "x" >> "$1"')
        rc, out, _ = run(["edit", "47", "--editor", ed, "--dry-run"], c)
        self.assertEqual(rc, 0)
        self.assertEqual(c.puts, [])
        self.assertIn("would PUT", out)

    def test_content_file_needs_no_editor(self):
        c = EditClient()
        f = Path(self.tmp) / "new.md"
        f.write_text("from a file\n")
        rc, out, _ = run(["edit", "47", "--content-file", str(f)], c)
        self.assertEqual(rc, 0)
        self.assertEqual(c.puts[0]["content"], "from a file\n")

    def test_temp_file_is_private_and_cleaned_up(self):
        """dir 700 / file 600 while the editor runs; gone afterwards."""
        mode_file = Path(self.tmp) / "mode.txt"
        ed = make_editor(self.tmp, f'stat -c "file=%a" "$1" > {mode_file}; '
                                   f'stat -c "dir=%a" "$(dirname "$1")" >> {mode_file}')
        c = EditClient()
        rc, out, _ = run(["edit", "47", "--editor", ed], c)
        self.assertEqual(rc, 0)
        modes = dict(line.split("=") for line in mode_file.read_text().split())
        self.assertEqual(modes["file"], "600")
        self.assertEqual(modes["dir"], "700")
        # nothing left behind after a successful write
        self.assertEqual(self.leftovers(), [])


class ReadOnlyTests(unittest.TestCase):
    """Spike 1's promise, pinned: reading can never write."""

    def test_read_commands_issue_only_get(self):
        c = EditClient()
        for argv in (["list"], ["show", "47"], ["show", "47", "--raw"],
                     ["search", "x"], ["tags"]):
            run(argv, c)
        verbs = {m for (m, *_rest) in c.calls}
        self.assertEqual(verbs, {"GET"}, f"non-GET call in a read command: {c.calls}")


if __name__ == "__main__":
    unittest.main()
