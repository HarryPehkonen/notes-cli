# hn — Harri's Notes from the terminal

Read and (soon) edit [Harri's Notes](https://harrisnotes.ca) from a shell, without a
browser. Python **standard library only**: no dependencies, no build step, one
executable file.

## Why

The web app is good at notes. It is not good at `grep`, at `| less`, at getting a
fenced block into an editor, or at opening a note from a terminal you are already
sitting in. `hn` is the thin end of that: read first, then edit in place with
`$EDITOR`.

## Status

| command | state |
|---|---|
| `hn list [--tag T] [--limit N] [--json]` | working |
| `hn show <id or part of a title> [--raw] [--json]` | working |
| `hn search <query> [--json]` | working |
| `hn tags` | working |
| `hn edit <id> [--editor E] [--content-file F] [--dry-run]` | working |
| `hn version` | working |
| new / tag / pin / archive | next — see Spikes |

## Install

    git clone https://github.com/HarryPehkonen/hn.git ~/src/hn
    ln -sf ~/src/hn/hn ~/.local/bin/hn     # or anywhere on $PATH
    hn version

## Auth

`hn` reads a personal API token from `~/.config/hn/auth.json`, mode **600** (directory 700):

    { "base_url": "https://harrisnotes.ca/api", "token": "nt_...", "name": "hn-macbook" }

It refuses to start if that file is group- or world-readable, never prints the token,
and never takes it on a command line. Override the path with `HN_AUTH_FILE` (the tests
use this). Tokens are minted per machine inside the Notes app, so revoking one machine
does not disturb the other.

## Use

    hn list --tag c++             # notes carrying a tag
    hn show 98                    # by id
    hn show conformance           # by part of the title (must be unique)
    hn show 98 --raw | vim -      # content only: no headers, no decoration
    hn search "json patch"        # full-text search, ranked
    hn tags                       # tags with note counts
    hn list --json | jq '.[0].id'

`hn` does not invoke `$PAGER` for you: `hn show 98 | less` is one keystroke more and
works with whatever pager you already use. `--raw` exists so `| vim -` gets exactly
the note body.

## Tests

    ./gate.sh          # syntax + 26 unit tests, offline, no dependencies

The API is faked, so the suite needs no network and no token — and it pins the
**contract** (`/tags/:id/notes` for listing by tag, `/search?q=`, the `{success, data}`
envelope) rather than whatever the server happens to do today. One manual smoke test
covers the live path:

    hn list && hn tags && hn show 98 --raw | head

## Editing safely

    hn edit 98                          # opens $EDITOR on a temp copy
    hn edit 98 --editor "nvim -u NONE"  # a specific editor
    hn edit 98 --content-file new.md    # no editor: take the content from a file
    hn edit 98 --dry-run                # say what would be sent, send nothing

`hn edit` never clobbers. The note carries an optimistic lock — its `updated_at` —
and hn sends the value it started from. Two guards protect you:

1. before writing, hn re-reads the note; if `updated_at` moved, it **refuses**;
2. if it still loses the race, the server answers **409 Conflict** and hn refuses.

On refusal, **nothing is written** and your edited text is kept on disk, with the
exact command to retry:

    hn: note 98 changed on the server since you started — NOTHING was written.
      server now: 2026-09-16T18:23:52.418Z  (31 bytes)
      your edits: /tmp/hn-edit-98-ab12cd34/note-98.md  (30 bytes — kept)
      re-run:     hn edit 98 --content-file /tmp/hn-edit-98-ab12cd34/note-98.md

The temp file is created in a private directory (dir 700, file 600) and removed after
a successful write. If the editor exits non-zero, or deletes the file, nothing is
sent either.

Measured, and worth knowing for any other tooling: the lock field the server honours
is **`updated_at`**. Sending `updatedAt`, `contentVersion` or `version` is accepted
*and ignored* — a client that sends one of those has no protection at all and will
silently overwrite a newer note. (`DELETE /api/notes/:id` soft-deletes: 204, the note
leaves the default list but is still readable by id.)

## Spikes

Built in risk order, as ops proposed:

1. **auth + read** — done (this commit).
2. **edit round-trip** (`$EDITOR`, and detect that the note changed underneath) — done.
   Verified live: an editor that writes the note from another session gets refused,
   the server's text survives and the user's edit is kept on disk.
3. **fzf picker** for `list`/`show` with no argument.
4. **Vim + install** polish.

## Licence

The Unlicense — public domain. See `LICENSE`.
