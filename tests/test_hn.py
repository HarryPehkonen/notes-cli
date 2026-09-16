#!/usr/bin/env python3
"""Tests for hn — no network needed.

    python3 -m unittest discover -s tests -v

The API is replaced by FakeClient, so these run offline and in CI. The one live
test is skipped unless HN_LIVE=1 (it talks to the real Notes API).
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

SRC = Path(__file__).resolve().parent.parent / "hn"
_loader = importlib.machinery.SourceFileLoader("hn", str(SRC))
_spec = importlib.util.spec_from_loader("hn", _loader)
hn = importlib.util.module_from_spec(_spec)
_loader.exec_module(hn)


NOTE_PINNED = {"id": 47, "title": "Things to do", "is_pinned": True, "is_archived": False,
               "updated_at": "2026-09-13T10:15:04.754Z", "content": "- water\n- chimney\n",
               "tags": []}
NOTE_TAGGED = {"id": 98, "title": "JSOM: conformance verdict", "is_pinned": False,
               "updated_at": "2026-09-16T05:00:00Z", "content": "# verdict\n\nbody\n",
               "tags": [{"id": 6, "name": "c++"}]}


class FakeClient:
    """Records every call and serves canned responses — the API seam."""

    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        if path in self.responses:
            return self.responses[path]
        if path == "/notes":
            return {"notes": [NOTE_PINNED, NOTE_TAGGED]}
        if path == "/tags":
            return [{"id": 6, "name": "c++", "note_count": 13},
                    {"id": 5, "name": "ai", "note_count": 9}]
        if path == "/tags/6/notes":
            return [NOTE_TAGGED]
        if path == "/search":
            return {"query": "x", "results": [NOTE_TAGGED]}
        if path.startswith("/notes/"):
            nid = int(path.split("/")[-1])
            return {47: NOTE_PINNED, 98: NOTE_TAGGED}[nid]
        raise AssertionError(f"unexpected path {path}")


def run(argv, client):
    """Call hn's commands with a fake client, capturing stdout/stderr."""
    args = hn.build_parser().parse_args(argv)
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = args.func(client, args)
    return rc, out.getvalue(), err.getvalue()


class AuthTests(unittest.TestCase):
    def _file(self, payload, mode=0o600):
        d = tempfile.mkdtemp()
        p = Path(d) / "auth.json"
        p.write_text(json.dumps(payload))
        os.chmod(p, mode)
        return p

    def test_missing_file_says_what_to_do(self):
        with self.assertRaises(hn.HnError) as cm:
            hn.load_auth("/nonexistent/auth.json")
        self.assertIn("no auth file", str(cm.exception))

    def test_world_readable_token_is_refused(self):
        p = self._file({"base_url": "https://x/api", "token": "nt_" + "a" * 40}, mode=0o644)
        with self.assertRaises(hn.HnError) as cm:
            hn.load_auth(p)
        self.assertIn("chmod 600", str(cm.exception))

    def test_missing_token_key(self):
        p = self._file({"base_url": "https://x/api"})
        with self.assertRaises(hn.HnError) as cm:
            hn.load_auth(p)
        self.assertIn("token", str(cm.exception))

    def test_ok_and_trailing_slash_stripped(self):
        token = "nt_" + "b" * 40
        p = self._file({"base_url": "https://harrisnotes.ca/api/", "token": token,
                        "name": "hn-test"})
        base, tok = hn.load_auth(p)
        self.assertEqual(base, "https://harrisnotes.ca/api")
        self.assertEqual(tok, token)

    def test_non_http_base_url_rejected(self):
        p = self._file({"base_url": "ftp://x", "token": "nt_" + "c" * 40})
        with self.assertRaises(hn.HnError):
            hn.load_auth(p)


class CommandTests(unittest.TestCase):
    def test_list_shows_pinned_marker_titles_and_tags(self):
        rc, out, _ = run(["list"], FakeClient())
        self.assertEqual(rc, 0)
        self.assertIn("*  47  Things to do", out)
        self.assertIn("98  JSOM: conformance verdict  [c++]", out)
        self.assertIn("2 note(s)", out)

    def test_list_by_tag_uses_the_tag_subresource(self):
        c = FakeClient()
        rc, out, _ = run(["list", "--tag", "c++"], c)
        self.assertEqual(rc, 0)
        self.assertEqual(c.calls[-1], ("GET", "/tags/6/notes", None))
        self.assertIn("JSOM", out)

    def test_list_unknown_tag_is_an_error(self):
        with self.assertRaises(hn.HnError) as cm:
            run(["list", "--tag", "nope"], FakeClient())
        self.assertIn("no tag named", str(cm.exception))

    def test_show_by_id(self):
        rc, out, _ = run(["show", "47"], FakeClient())
        self.assertEqual(rc, 0)
        self.assertIn("#47  Things to do", out)
        self.assertIn("pinned", out)

    def test_show_by_title_substring(self):
        rc, out, _ = run(["show", "conformance"], FakeClient())
        self.assertEqual(rc, 0)
        self.assertIn("#98", out)

    def test_show_unknown_title_is_an_error(self):
        with self.assertRaises(hn.HnError) as cm:
            run(["show", "zzzz"], FakeClient())
        self.assertIn("no note matches", str(cm.exception))

    def test_show_raw_is_content_only(self):
        rc, out, _ = run(["show", "47", "--raw"], FakeClient())
        self.assertEqual(rc, 0)
        self.assertEqual(out, "- water\n- chimney\n")

    def test_show_json_round_trips(self):
        rc, out, _ = run(["show", "47", "--json"], FakeClient())
        self.assertEqual(json.loads(out)["id"], 47)

    def test_search_uses_search_endpoint(self):
        c = FakeClient()
        rc, out, _ = run(["search", "conformance"], c)
        self.assertEqual(c.calls[-1], ("GET", "/search", {"q": "conformance"}))
        self.assertIn("1 result(s)", out)

    def test_tags_sorted_by_count(self):
        rc, out, _ = run(["tags"], FakeClient())
        self.assertEqual(rc, 0)
        self.assertLess(out.index("c++"), out.index("ai"))

    def test_token_never_appears_in_output(self):
        """The token must not leak into stdout/stderr, even on success."""
        token = "nt_" + "d" * 40
        c = FakeClient()
        c.token = token
        for argv in (["list"], ["tags"], ["show", "47"], ["search", "x"]):
            _, out, err = run(argv, c)
            self.assertNotIn(token, out)
            self.assertNotIn(token, err)


if __name__ == "__main__":
    unittest.main()
