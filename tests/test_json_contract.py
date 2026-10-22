#!/usr/bin/env python3
"""The --json contract, pinned. Offline: urlopen() is replaced, the Client is real.

One rule, two shapes:

* `--json` prints the **unwrapped** `data` — a note object for the note-returning
  commands (so a successful create reads as a success: `jq .id`, and there is no
  `data` key to mistake it for a failure), a bare array for list/search/tags/versions.
* `--json-envelope` (implies `--json`) prints the server's **literal** response,
  `{"success": true, "data": ..., "meta": ...}` — the API's own shape, and the only
  route to `meta.total` / `meta.hasMore`, which the default output never carries.

These tests drive the real Client over a stubbed transport, so the unwrapping inside
`Client.request()` is exercised rather than mocked away.
"""

import json
import tempfile
import unittest
import urllib.parse
import urllib.request
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import test_hn  # noqa: E402
from test_hn import run  # noqa: E402

notes = test_hn.notes

NOTE = {"id": 127, "title": "T", "content": "b\n", "tags": []}
# The API's own shapes: every response is wrapped, and GET /notes carries a page.
LIST = {"success": True, "data": {"notes": [NOTE]},
        "meta": {"total": 313, "hasMore": True, "limit": 1, "offset": 0}}
ONE = {"success": True, "data": NOTE, "meta": {}}
POSTED = {"success": True, "data": NOTE}
PUT = {"success": True, "data": {"id": 127, "title": "N", "content": "b\n"}}
TAGS = {"success": True, "data": [{"id": 6, "name": "c++", "note_count": 13}]}
TAG_NOTES = {"success": True, "data": [NOTE], "meta": {"total": 1}}
SEARCH = {"success": True, "data": {"query": "t", "results": [NOTE]}, "meta": {"total": 1}}
VERSIONS = {"success": True, "data": [{"id": 11, "title": "Old", "content": "old\n",
                                       "created_at": "t1"}]}


class _Response:
    """What urlopen() returns: a context manager with .read()."""

    def __init__(self, payload):
        self._raw = b"" if payload is None else json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Transport:
    """A urlopen() replacement: canned envelopes, every request recorded.

    A response can be keyed by path alone, or by ("METHOD", path) when one path
    answers differently per method (GET a note, then PUT it).
    """

    BASE = "/api"

    def __init__(self, responses):
        self.responses = responses
        self.requests = []                  # (method, path)

    def __call__(self, req, timeout=None):
        path = urllib.parse.urlsplit(req.full_url).path
        self.requests.append((req.method, path))
        for key in ((req.method, path), path):
            if key in self.responses:
                return _Response(self.responses[key])
        raise AssertionError(f"unexpected request {req.method} {path}")

    @property
    def last(self):
        return self.requests[-1]


@contextmanager
def serving(responses):
    """A real Client whose network is the stub above."""
    t = Transport(responses)
    c = notes.Client("https://api.example/api", "nt_test", timeout=5)
    with mock.patch.object(urllib.request, "urlopen", t):
        yield t, c


def body_file(text="b\n"):
    p = Path(tempfile.mkdtemp()) / "body.md"
    p.write_text(text)
    return str(p)


class UnwrappedIsTheDefault(unittest.TestCase):
    """The shape every existing script and the README's jq examples rely on."""

    def test_client_request_returns_only_data(self):
        with serving({"/api/notes": LIST}) as (t, c):
            self.assertEqual(c.get("/notes"), {"notes": [NOTE]})

    def test_list_json_is_a_bare_array(self):
        with serving({"/api/notes": LIST}) as (t, c):
            rc, out, _ = run(["list", "--json"], c)
        self.assertEqual(rc, 0)
        parsed = json.loads(out)                  # the README: notes list --json | jq '.[0].id'
        self.assertIsInstance(parsed, list)
        self.assertEqual(parsed[0]["id"], 127)

    def test_create_json_has_a_top_level_id(self):
        argv = ["create", "--title", "T", "--body-file", body_file(), "--json"]
        with serving({"/api/notes": POSTED}) as (t, c):
            rc, out, _ = run(argv, c)
        self.assertEqual(rc, 0)
        parsed = json.loads(out)
        self.assertEqual(parsed["id"], 127)       # not parsed["data"]["id"]
        self.assertNotIn("data", parsed)
        self.assertNotIn("success", parsed)
        self.assertNotIn("meta", parsed)

    def test_meta_is_unreachable_in_the_default_shape(self):
        with serving({"/api/notes": LIST}) as (t, c):
            _, out, _ = run(["list", "--json"], c)
        self.assertNotIn("313", out)              # meta.total stays out of the way


class EnvelopeIsOptIn(unittest.TestCase):
    def test_list_envelope_is_the_servers_literal_body(self):
        with serving({"/api/notes": LIST}) as (t, c):
            rc, out, _ = run(["list", "--json-envelope"], c)
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), LIST)

    def test_list_envelope_recovers_meta(self):
        with serving({"/api/notes": LIST}) as (t, c):
            _, out, _ = run(["list", "--json-envelope"], c)
        meta = json.loads(out)["meta"]
        self.assertEqual(meta["total"], 313)
        self.assertIs(meta["hasMore"], True)

    def test_the_flag_implies_json(self):
        with serving({"/api/notes": LIST}) as (t, c):
            _, out, _ = run(["list", "--json-envelope"], c)   # no --json given
        self.assertIs(json.loads(out)["success"], True)

    def test_create_envelope_answers_data_id(self):
        """The idiom that failed: a successful POST read as a failure."""
        argv = ["create", "--title", "T", "--body-file", body_file(), "--json-envelope"]
        with serving({"/api/notes": POSTED}) as (t, c):
            _, out, _ = run(argv, c)
        parsed = json.loads(out)
        self.assertIs(parsed["success"], True)
        self.assertEqual(parsed["data"]["id"], 127)

    def test_read_commands_expose_their_envelope(self):
        cases = [
            (["show", "127"], ONE, "/api/notes/127"),
            (["search", "t"], SEARCH, "/api/search"),
            (["tags"], TAGS, "/api/tags"),
            (["versions", "127"], VERSIONS, "/api/notes/127/versions"),
        ]
        for argv, envelope, path in cases:
            with self.subTest(argv=argv), serving({path: envelope}) as (t, c):
                rc, out, _ = run(argv + ["--json-envelope"], c)
                self.assertEqual(rc, 0)
                self.assertEqual(json.loads(out), envelope)

    def test_a_response_with_no_body_prints_null(self):
        with serving({("DELETE", "/api/notes/127"): None}) as (t, c):
            rc, out, _ = run(["archive", "127", "--json-envelope"], c)
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), None)


class TheEnvelopePrintedIsTheCommandsOwn(unittest.TestCase):
    """--json-envelope must never print a lookup's response instead of the act's."""

    def test_create_with_a_tag_prints_the_post_not_the_tag_lookup(self):
        argv = ["create", "--title", "T", "--body-file", body_file(), "--tag", "c++",
                "--json-envelope"]
        with serving({"/api/tags": TAGS, "/api/notes": POSTED}) as (t, c):
            _, out, _ = run(argv, c)
        self.assertEqual(t.requests, [("GET", "/api/tags"), ("POST", "/api/notes")])
        self.assertEqual(json.loads(out), POSTED)

    def test_list_by_tag_prints_the_page_of_that_tag(self):
        with serving({"/api/tags": TAGS, "/api/tags/6/notes": TAG_NOTES}) as (t, c):
            _, out, _ = run(["list", "--tag", "c++", "--json-envelope"], c)
        self.assertEqual(json.loads(out), TAG_NOTES)

    def test_show_by_title_prints_the_note_not_the_listing(self):
        with serving({"/api/notes": LIST, "/api/notes/127": ONE}) as (t, c):
            _, out, _ = run(["show", "T", "--json-envelope"], c)
        self.assertEqual(t.last, ("GET", "/api/notes/127"))
        self.assertEqual(json.loads(out), ONE)

    def test_writes_print_their_own_response(self):
        cases = [
            (["set", "127", "--title", "N"], ("PUT", "/api/notes/127")),
            (["append", "127", "--body-file", body_file("more\n")], ("PUT", "/api/notes/127")),
            (["prepend", "127", "--body-file", body_file("top\n")], ("PUT", "/api/notes/127")),
            (["restore", "127", "11"], ("PUT", "/api/notes/127")),
            (["tag", "127", "c++"], ("PUT", "/api/notes/127/tags/6")),
            (["untag", "127", "c++"], ("DELETE", "/api/notes/127/tags/6")),
            (["archive", "127"], ("DELETE", "/api/notes/127")),
        ]
        for argv, write in cases:
            responses = {("GET", "/api/notes/127"): ONE,
                         "/api/notes/127": ONE,
                         "/api/notes/127/versions": VERSIONS,
                         "/api/notes/127/tags/6": PUT,
                         "/api/tags": TAGS}
            responses[write] = PUT
            with self.subTest(argv=argv), serving(responses) as (t, c):
                rc, out, _ = run(argv + ["--json-envelope"], c)
                self.assertEqual(rc, 0)
                self.assertEqual(t.last, write)
                self.assertEqual(json.loads(out), PUT)

    def test_the_readme_pipeline_is_unaffected_by_the_flag(self):
        with serving({"/api/notes": LIST}) as (t, c):
            _, unwrapped, _ = run(["list", "--json"], c)
            _, enveloped, _ = run(["list", "--json-envelope"], c)
        self.assertEqual(json.loads(unwrapped)[0]["id"], 127)
        self.assertEqual(json.loads(enveloped)["data"]["notes"][0]["id"], 127)


class HelpAgreesWithTheContract(unittest.TestCase):
    def _help(self, argv):
        out = StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit):
            notes.build_parser().parse_args(argv + ["--help"])
        return out.getvalue()

    def test_help_names_both_shapes(self):
        text = self._help(["list"])
        self.assertIn("--json-envelope", text)
        self.assertIn("data", text)

    def test_every_json_command_offers_the_envelope(self):
        parser = notes.build_parser()
        sub = parser._subparsers._group_actions[0].choices      # argparse has no public way
        for name, sp in sub.items():
            opts = {o for a in sp._actions for o in a.option_strings}
            if "--json" in opts:
                self.assertIn("--json-envelope", opts, f"{name} lacks --json-envelope")


if __name__ == "__main__":
    unittest.main()
