#!/usr/bin/env python3
"""Tests for the fzf picker — which must be an optional convenience, never a need.

fzf is simulated by a stub script, and "is there a terminal?" is overridden, so these
run offline in CI with no fzf installed and no tty.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import test_hn
from test_edit import EditClient
from test_hn import FakeClient, run

notes = test_hn.notes


def stub_fzf(tmp, behaviour):
    """A fake fzf: records the candidate lines it was handed, then behaves."""
    stdin_dump = Path(tmp) / "fzf-stdin.txt"
    marker = Path(tmp) / "fzf-was-run"
    body = {
        # choose the Nth line, like a user pressing Enter
        "choose": f'cat > {stdin_dump}; touch {marker}; sed -n "2p" {stdin_dump}',
        # Esc / Ctrl-C
        "cancel": f'cat > {stdin_dump}; touch {marker}; exit 130',
    }[behaviour]
    p = Path(tmp) / "fzf"
    p.write_text("#!/bin/sh\n" + body + "\n")
    os.chmod(p, 0o755)
    return str(p), stdin_dump, marker


class PickerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._saved = (notes.can_pick, os.environ.get("HN_FZF"))
        notes.can_pick = lambda: True            # pretend we have a terminal

    def tearDown(self):
        notes.can_pick, old = self._saved
        if old is None:
            os.environ.pop("HN_FZF", None)
        else:
            os.environ["HN_FZF"] = old

    def test_no_fzf_lists_notes_and_explains(self):
        notes.can_pick = lambda: False           # no fzf, or no terminal
        os.environ.pop("HN_FZF", None)
        p = Path(self.tmp) / "path-without-fzf"
        p.mkdir()
        old_path = os.environ["PATH"]
        os.environ["PATH"] = str(p)           # guarantee fzf is not found
        try:
            rc, out, err = run(["show"], FakeClient())
        finally:
            os.environ["PATH"] = old_path
        self.assertEqual(rc, 1)
        self.assertIn("Things to do", out)              # the list still appears
        self.assertIn("fzf is not installed", err)      # and says why it could not pick
        self.assertIn("notes show", err)

    def test_choice_from_fzf_is_used(self):
        fzf, stdin_dump, _ = stub_fzf(self.tmp, "choose")
        os.environ["HN_FZF"] = fzf
        rc, out, _ = run(["show"], FakeClient())
        self.assertEqual(rc, 0)
        # the stub picks line 2, whose id is 98 -> that note is what we show
        self.assertIn("#98", out)
        # the contract: candidates are "<id>\t<label>", so the id reads back exactly
        first = stdin_dump.read_text().splitlines()[0]
        self.assertRegex(first, r"^\d+\t")

    def test_cancelled_picker_does_nothing(self):
        fzf, _, marker = stub_fzf(self.tmp, "cancel")
        os.environ["HN_FZF"] = fzf
        rc, out, err = run(["show"], FakeClient())
        self.assertEqual(rc, 1)
        self.assertTrue(marker.exists(), "the picker should have been offered")
        self.assertIn("fzf is not installed", err)      # same explanation path

    def test_cancelled_edit_writes_nothing(self):
        """The one that matters: Esc in the picker must not touch the server."""
        fzf, _, _ = stub_fzf(self.tmp, "cancel")
        os.environ["HN_FZF"] = fzf
        c = EditClient()
        rc, out, err = run(["edit"], c)
        self.assertEqual(rc, 1)
        self.assertEqual(c.puts, [], "a cancelled picker must never write")

    def test_no_pick_flag_lists_and_never_runs_fzf(self):
        fzf, _, marker = stub_fzf(self.tmp, "choose")
        os.environ["HN_FZF"] = fzf
        rc, out, _ = run(["show", "--no-pick"], FakeClient())
        self.assertEqual(rc, 1)
        self.assertFalse(marker.exists(), "--no-pick must not run the picker")
        self.assertIn("Things to do", out)

    def test_an_argument_never_opens_the_picker(self):
        fzf, _, marker = stub_fzf(self.tmp, "choose")
        os.environ["HN_FZF"] = fzf
        rc, out, _ = run(["show", "47"], FakeClient())
        self.assertEqual(rc, 0)
        self.assertFalse(marker.exists(), "an explicit note must not open a picker")
        self.assertIn("#47", out)

    def test_pick_then_edit_goes_through_the_lock_path(self):
        """Picking a note then editing it still sends the lock."""
        fzf, _, _ = stub_fzf(self.tmp, "choose")     # picks line 2 -> id 98
        os.environ["HN_FZF"] = fzf
        c = EditClient(note={"id": 98, "title": "JSOM: conformance verdict",
                             "updated_at": "2026-09-16T05:00:00Z", "content": "old\n"})
        out_file = Path(self.tmp) / "new.md"
        out_file.write_text("new content from a picked note\n")
        rc, out, err = run(["edit", "--content-file", str(out_file)], c)
        self.assertEqual(rc, 0, err)
        self.assertEqual(len(c.puts), 1)
        self.assertEqual(c.puts[0]["updated_at"], "2026-09-16T05:00:00Z")


if __name__ == "__main__":
    unittest.main()
