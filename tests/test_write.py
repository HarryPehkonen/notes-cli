#!/usr/bin/env python3
"""Tests for the write surface: create, append, prepend, set, tag, untag, archive,
versions, restore. Offline: Client.request() is the seam and is faked here."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import test_client  # noqa: E402
from test_client import NOTE_PINNED, NOTE_TAGGED, FakeClient, run  # noqa: E402

notes = test_client.notes


class WriteClient(FakeClient):
    """FakeClient plus request(): reads delegate to get(), writes are recorded."""

    def __init__(self, versions=None):
        super().__init__()
        self.writes = []          # (method, path, body)
        self.versions = versions

    def request(self, method, path, params=None, body=None):
        if method == "GET":
            return self.get(path, params)
        self.writes.append((method, path, body))
        if method == "POST":
            return {"id": 200, "title": body["title"], "content": body["content"]}
        if method == "PUT" and path.endswith("/tags/6") or method == "DELETE":
            return None
        return {"id": int(path.split("/")[2]), **(body or {})}

    def get(self, path, params=None):
        if path.endswith("/versions"):
            self.calls.append(("GET", path, params))
            return self.versions if self.versions is not None else []
        return super().get(path, params)


def body_file(text):
    d = tempfile.mkdtemp()
    p = Path(d) / "body.md"
    p.write_text(text)
    return str(p)


class CreateTests(unittest.TestCase):
    def test_create_posts_title_content_and_tag_ids(self):
        c = WriteClient()
        rc, out, _ = run(["create", "--title", "T", "--body-file", body_file("hello\n"),
                          "--tag", "c++", "--tag", "ai"], c)
        self.assertEqual(rc, 0)
        self.assertEqual(c.writes, [("POST", "/notes",
                                     {"title": "T", "content": "hello\n",
                                      "tags": [6, 5], "format": "markdown"})])
        self.assertIn("200", out)

    def test_create_format_groff_is_sent_and_reported(self):
        c = WriteClient()
        rc, out, _ = run(["create", "--title", "Pancakes",
                          "--body-file", body_file('.RECIPE "Pancakes"\n'),
                          "--format", "groff"], c)
        self.assertEqual(rc, 0)
        self.assertEqual(c.writes, [("POST", "/notes",
                                     {"title": "Pancakes",
                                      "content": '.RECIPE "Pancakes"\n',
                                      "tags": [], "format": "groff"})])
        self.assertIn("[groff]", out)

    def test_create_format_defaults_to_markdown(self):
        c = WriteClient()
        _, out, _ = run(["create", "--title", "T", "--body-file", body_file("x\n")], c)
        self.assertEqual(c.writes[0][2]["format"], "markdown")
        self.assertNotIn("[groff]", out)

    def test_task_with_groff_is_refused_before_any_request(self):
        c = WriteClient()
        with self.assertRaises(notes.NotesError) as cm:
            run(["create", "--title", "T", "--body-file", body_file("x\n"),
                 "--format", "groff", "--task", "chop"], c)
        self.assertIn("--task", str(cm.exception))
        self.assertEqual(c.writes, [])

    def test_unknown_format_is_rejected_by_the_parser(self):
        c = WriteClient()
        with self.assertRaises(SystemExit) as cm:
            run(["create", "--title", "T", "--body-file", body_file("x\n"),
                 "--format", "grolf"], c)
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(c.writes, [])

    def test_tag_name_resolution_cpp_is_6(self):
        c = WriteClient()
        run(["create", "--title", "T", "--body-file", body_file("x\n"), "--tag", "c++"], c)
        self.assertEqual(c.writes[0][2]["tags"], [6])

    def test_unknown_tag_is_an_error_and_writes_nothing(self):
        c = WriteClient()
        with self.assertRaises(notes.NotesError):
            run(["create", "--title", "T", "--body-file", body_file("x"), "--tag", "nope"], c)
        self.assertEqual(c.writes, [])

    def test_tasks_become_checkboxes_appended_to_content(self):
        c = WriteClient()
        run(["create", "--title", "T", "--body-file", body_file("intro\n"),
             "--task", "one", "--task", "two"], c)
        self.assertEqual(c.writes[0][2]["content"], "intro\n- [ ] one\n- [ ] two\n")

    def test_tasks_after_body_without_trailing_newline(self):
        c = WriteClient()
        run(["create", "--title", "T", "--body-file", body_file("intro"), "--task", "one"], c)
        self.assertEqual(c.writes[0][2]["content"], "intro\n- [ ] one\n")

    def test_body_file_dash_reads_stdin(self):
        c = WriteClient()
        old = sys.stdin
        sys.stdin = io.StringIO("from stdin\n")
        try:
            run(["create", "--title", "T", "--body-file", "-"], c)
        finally:
            sys.stdin = old
        self.assertEqual(c.writes[0][2]["content"], "from stdin\n")

    def test_body_file_is_required(self):
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            notes.build_parser().parse_args(["create", "--title", "T"])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("--body-file", err.getvalue())

    def test_json_prints_api_response(self):
        c = WriteClient()
        _, out, _ = run(["create", "--title", "T", "--body-file", body_file("b"), "--json"], c)
        self.assertEqual(json.loads(out)["id"], 200)


class EditContentTests(unittest.TestCase):
    def test_append_puts_title_and_content_only(self):
        c = WriteClient()
        rc, _, _ = run(["append", "47", "--body-file", body_file("- milk\n")], c)
        self.assertEqual(rc, 0)
        self.assertEqual(c.writes, [("PUT", "/notes/47", {
            "title": "Things to do", "content": "- water\n- chimney\n- milk\n"})])

    def test_append_adds_missing_newline_separator(self):
        c = WriteClient()
        c.responses["/notes/47"] = dict(NOTE_PINNED, content="no newline")
        run(["append", "47", "--body-file", body_file("more\n")], c)
        self.assertEqual(c.writes[0][2]["content"], "no newline\nmore\n")

    def test_prepend(self):
        c = WriteClient()
        run(["prepend", "47", "--body-file", body_file("top\n")], c)
        self.assertEqual(c.writes, [("PUT", "/notes/47", {
            "title": "Things to do", "content": "top\n- water\n- chimney\n"})])

    def test_append_stdin(self):
        c = WriteClient()
        old = sys.stdin
        sys.stdin = io.StringIO("piped\n")
        try:
            run(["append", "47", "--body-file", "-"], c)
        finally:
            sys.stdin = old
        self.assertTrue(c.writes[0][2]["content"].endswith("piped\n"))

    def test_append_requires_body_file(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            notes.build_parser().parse_args(["append", "47"])

    def test_set_title_only_keeps_content(self):
        c = WriteClient()
        run(["set", "47", "--title", "New"], c)
        self.assertEqual(c.writes, [("PUT", "/notes/47", {
            "title": "New", "content": "- water\n- chimney\n"})])

    def test_set_body_only_keeps_title(self):
        c = WriteClient()
        run(["set", "47", "--body-file", body_file("fresh\n")], c)
        self.assertEqual(c.writes, [("PUT", "/notes/47", {
            "title": "Things to do", "content": "fresh\n"})])

    def test_set_with_nothing_to_set_is_an_error(self):
        c = WriteClient()
        with self.assertRaises(notes.NotesError):
            run(["set", "47"], c)
        self.assertEqual(c.writes, [])

    def test_json_flag(self):
        c = WriteClient()
        _, out, _ = run(["set", "47", "--title", "N", "--json"], c)
        self.assertEqual(json.loads(out)["title"], "N")


class TagArchiveTests(unittest.TestCase):
    def test_tag_resolves_name_and_puts(self):
        c = WriteClient()
        rc, out, _ = run(["tag", "47", "c++"], c)
        self.assertEqual(rc, 0)
        self.assertEqual(c.writes, [("PUT", "/notes/47/tags/6", None)])
        self.assertIn("c++", out)

    def test_untag_deletes(self):
        c = WriteClient()
        run(["untag", "98", "c++"], c)
        self.assertEqual(c.writes, [("DELETE", "/notes/98/tags/6", None)])

    def test_tag_unknown_name_errors(self):
        c = WriteClient()
        with self.assertRaises(notes.NotesError):
            run(["tag", "47", "nope"], c)
        self.assertEqual(c.writes, [])

    def test_archive_deletes_and_confirms(self):
        c = WriteClient()
        rc, out, _ = run(["archive", "47"], c)
        self.assertEqual(rc, 0)
        self.assertEqual(c.writes, [("DELETE", "/notes/47", None)])
        self.assertIn("archived", out)
        self.assertIn("47", out)

    def test_archive_json(self):
        _, out, _ = run(["archive", "47", "--json"], WriteClient())
        json.loads(out)


VERSIONS = [{"id": 11, "title": "Old", "content": "old text\n", "created_at": "t1"},
            {"id": 12, "title": "Older", "content": "older\n", "created_at": "t0"}]


class VersionTests(unittest.TestCase):
    def test_versions_lists(self):
        c = WriteClient(versions=VERSIONS)
        rc, out, _ = run(["versions", "47"], c)
        self.assertEqual(rc, 0)
        self.assertIn(("GET", "/notes/47/versions", None), c.calls)
        self.assertIn("11", out)

    def test_versions_json(self):
        _, out, _ = run(["versions", "47", "--json"], WriteClient(versions=VERSIONS))
        self.assertEqual(json.loads(out), VERSIONS)

    def test_versions_accepts_wrapped_dict(self):
        _, out, _ = run(["versions", "47", "--json"],
                        WriteClient(versions={"versions": VERSIONS}))
        self.assertEqual(json.loads(out), VERSIONS)

    def test_restore_puts_that_versions_content(self):
        c = WriteClient(versions=VERSIONS)
        rc, out, _ = run(["restore", "47", "11"], c)
        self.assertEqual(rc, 0)
        self.assertEqual(c.writes, [("PUT", "/notes/47", {
            "title": "Old", "content": "old text\n"})])

    def test_restore_unknown_version_errors(self):
        c = WriteClient(versions=VERSIONS)
        with self.assertRaises(notes.NotesError):
            run(["restore", "47", "99"], c)
        self.assertEqual(c.writes, [])

    def test_restore_no_versions_errors(self):
        c = WriteClient(versions=[])
        with self.assertRaises(notes.NotesError) as cm:
            run(["restore", "47", "1"], c)
        self.assertIn("no saved versions", str(cm.exception))
        self.assertEqual(c.writes, [])


if __name__ == "__main__":
    unittest.main()
