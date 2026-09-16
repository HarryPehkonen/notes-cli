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
| `hn version` | working |
| edit / new / tag / pin / archive | next — see Spikes |

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

    ./gate.sh          # syntax + 16 unit tests, offline, no dependencies

The API is faked, so the suite needs no network and no token — and it pins the
**contract** (`/tags/:id/notes` for listing by tag, `/search?q=`, the `{success, data}`
envelope) rather than whatever the server happens to do today. One manual smoke test
covers the live path:

    hn list && hn tags && hn show 98 --raw | head

## Spikes

Built in risk order, as ops proposed:

1. **auth + read** — done (this commit).
2. **edit round-trip** (`$EDITOR`, and detect that the note changed underneath) — next.
   This is the data-integrity one; it gets a throwaway note and a 409 test.
3. **fzf picker** for `list`/`show` with no argument.
4. **Vim + install** polish.

## Licence

The Unlicense — public domain. See `LICENSE`.
