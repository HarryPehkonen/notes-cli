#!/usr/bin/env python3
"""Auth precedence, profiles and the setup wizard. HOME is redirected to a temp dir."""

import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import test_client  # noqa: E402

notes = test_client.notes
KEYS = ("HOME", "HN_AUTH_FILE", "NOTES_TOKEN", "NOTES_BASE_URL")


class AuthEnv(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in KEYS}
        self.home = Path(tempfile.mkdtemp())
        os.environ["HOME"] = str(self.home)
        for k in KEYS[1:]:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def write(self, rel, base, token, mode=0o600):
        p = self.home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"base_url": base, "token": token}))
        os.chmod(p, mode)
        return p


class PrecedenceTests(AuthEnv):
    def test_new_path(self):
        self.write(".config/notes-cli/auth.json", "https://new/api", "tnew")
        self.assertEqual(notes.load_auth(), ("https://new/api", "tnew"))

    def test_legacy_fallback(self):
        self.write(".config/hn/auth.json", "https://old/api", "told")
        self.assertEqual(notes.load_auth(), ("https://old/api", "told"))

    def test_new_beats_legacy(self):
        self.write(".config/hn/auth.json", "https://old/api", "told")
        self.write(".config/notes-cli/auth.json", "https://new/api", "tnew")
        self.assertEqual(notes.load_auth()[1], "tnew")

    def test_profile_path(self):
        self.write(".config/notes-cli/auth.json", "https://new/api", "tnew")
        self.write(".config/notes-cli/auth.work.json", "https://work/api", "twork")
        self.assertEqual(notes.load_auth(profile="work"), ("https://work/api", "twork"))

    def test_missing_profile_does_not_fall_back(self):
        self.write(".config/notes-cli/auth.json", "https://new/api", "tnew")
        with self.assertRaises(notes.NotesError) as cm:
            notes.load_auth(profile="nope")
        self.assertIn("auth.nope.json", str(cm.exception))

    def test_bad_profile_name_rejected(self):
        with self.assertRaises(notes.NotesError):
            notes.load_auth(profile="../evil")

    def test_env_token_beats_files_and_profile(self):
        self.write(".config/notes-cli/auth.json", "https://new/api", "tnew")
        self.write(".config/notes-cli/auth.w.json", "https://w/api", "tw")
        os.environ["NOTES_TOKEN"] = "tenv"
        self.assertEqual(notes.load_auth(profile="w"),
                         ("https://harrisnotes.ca/api", "tenv"))

    def test_env_base_url(self):
        os.environ["NOTES_TOKEN"] = "tenv"
        os.environ["NOTES_BASE_URL"] = "http://localhost:3000/api/"
        self.assertEqual(notes.load_auth(), ("http://localhost:3000/api", "tenv"))

    def test_env_base_url_must_be_http(self):
        os.environ["NOTES_TOKEN"] = "tenv"
        os.environ["NOTES_BASE_URL"] = "ftp://x"
        with self.assertRaises(notes.NotesError):
            notes.load_auth()

    def test_legacy_auth_file_beats_env_token(self):
        p = self.write("custom.json", "https://custom/api", "tcustom")
        os.environ["HN_AUTH_FILE"] = str(p)
        os.environ["NOTES_TOKEN"] = "tenv"
        self.assertEqual(notes.load_auth(), ("https://custom/api", "tcustom"))

    def test_mode_still_enforced_on_new_path(self):
        self.write(".config/notes-cli/auth.json", "https://new/api", "tnew", mode=0o644)
        with self.assertRaises(notes.NotesError) as cm:
            notes.load_auth()
        self.assertIn("chmod 600", str(cm.exception))

    def test_nothing_configured_points_at_setup(self):
        with self.assertRaises(notes.NotesError) as cm:
            notes.load_auth()
        self.assertIn("notes setup", str(cm.exception))


class SetupTests(AuthEnv):
    def run_setup(self, argv, answers, secret="nt_secret"):
        args = notes.build_parser().parse_args(argv)
        it = iter(answers)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = notes.cmd_setup(args, ask=lambda prompt: next(it),
                                 ask_secret=lambda prompt: secret)
        return rc, out.getvalue() + err.getvalue()

    def test_writes_600_in_700_dir(self):
        rc, shown = self.run_setup(["setup"], ["https://me.example/api/"])
        self.assertEqual(rc, 0)
        p = self.home / ".config/notes-cli/auth.json"
        self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(p.parent.stat().st_mode), 0o700)
        self.assertEqual(json.loads(p.read_text()),
                         {"base_url": "https://me.example/api", "token": "nt_secret"})
        self.assertNotIn("nt_secret", shown)
        self.assertEqual(notes.load_auth(), ("https://me.example/api", "nt_secret"))

    def test_blank_url_uses_default(self):
        self.run_setup(["setup"], [""])
        d = json.loads((self.home / ".config/notes-cli/auth.json").read_text())
        self.assertEqual(d["base_url"], "https://harrisnotes.ca/api")

    def test_profile(self):
        self.run_setup(["--profile", "work", "setup"], ["https://w/api"])
        self.assertTrue((self.home / ".config/notes-cli/auth.work.json").exists())
        self.run_setup(["setup", "--profile", "home"], ["https://h/api"])
        self.assertTrue((self.home / ".config/notes-cli/auth.home.json").exists())

    def test_empty_token_rejected(self):
        with self.assertRaises(notes.NotesError):
            self.run_setup(["setup"], [""], secret="  ")

    def test_bad_url_rejected_and_nothing_written(self):
        with self.assertRaises(notes.NotesError):
            self.run_setup(["setup"], ["ftp://x"])
        self.assertFalse((self.home / ".config/notes-cli/auth.json").exists())


if __name__ == "__main__":
    unittest.main()
