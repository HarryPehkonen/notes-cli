# notes — the CLI for a Notes server

A command-line client for any [Notes](https://harrisnotes.ca)-compatible server: read,
search, edit, create, tag and archive notes from a shell, without a browser. Python
**standard library only**: no dependencies, no build step, one executable file.

Version 1.0.0.

## Make it yours

- **Point it at your server.** `notes setup` asks for a base URL. Use
  `https://harrisnotes.ca/api`, or any Notes deployment you run yourself — self-hosting
  is a first-class setup, not an afterthought. Nothing in the client is tied to one host.
- **Alias it to something short.** The binary is `notes`; give it a shorter name if you like:
  `alias n=notes`, or `ln -s ~/src/notes/notes ~/.local/bin/n`.
- **Several servers?** `notes --profile work list` reads
  `~/.config/notes-cli/auth.work.json`; `notes setup --profile work` creates it.
- **Optional niceties, never requirements:** `$EDITOR` (or `$VISUAL`, `$NOTES_EDITOR`) for
  `notes edit`; [fzf](https://github.com/junegunn/fzf) for the no-argument picker;
  `NO_COLOR` is honoured (notes prints no colour today, so it is always safe).

## Install

    git clone https://github.com/HarryPehkonen/notes-cli.git ~/src/notes
    ln -sf ~/src/notes/notes ~/.local/bin/notes     # or anywhere on $PATH
    notes setup
    notes version

## Packaging

The deb and rpm published in the pehkonen.dev repo are built from this repo:

    scripts/package.sh            # dist/notes-cli_1.0.0_all.deb + notes-cli-1.0.0-1.noarch.rpm

Both stages assert their contents (exactly /usr/bin/notes, the man page, and
the copyright file); the deb matches the published package's control fields.

## Auth

Run `notes setup`: it prompts for the base URL (default `https://harrisnotes.ca/api`)
and the token (hidden input, never echoed, never on a command line) and writes
`~/.config/notes-cli/auth.json` with mode **600** in a directory of mode 700:

    { "base_url": "https://harrisnotes.ca/api", "token": "nt_..." }

Where credentials come from, highest priority first:

1. `NOTES_AUTH_FILE` — explicit path to an auth file (the tests use this)
2. `NOTES_TOKEN` (with `NOTES_BASE_URL`, default `https://harrisnotes.ca/api`) — env
   vars win over any file in the config directory; handy for CI and containers
3. `--profile NAME` — `~/.config/notes-cli/auth.NAME.json`
4. `~/.config/notes-cli/auth.json`

`notes` refuses to use an auth file that is group- or world-readable, and never prints
the token. Tokens are minted per machine inside the Notes app, so revoking one machine
does not disturb the others.

## Commands

| command | what it does |
|---|---|
| `notes list [--tag T] [--limit N] [--json]` | list notes, pinned first |
| `notes show [<id or part of a title>] [--raw] [--json] [--no-pick]` | show one note |
| `notes search <query> [--json]` | full-text search |
| `notes tags [--json]` | tags with note counts |
| `notes edit [<id>] [--editor E] [--content-file F] [--dry-run]` | edit in `$EDITOR`, never clobbers |
| `notes create --title T --body-file F [--tag t]... [--task "..."]... [--format {markdown,groff}] [--json]` | new note |
| `notes append ID --body-file F [--json]` | add text at the end |
| `notes prepend ID --body-file F [--json]` | add text at the start |
| `notes set ID [--title T] [--body-file F] [--json]` | replace title and/or content |
| `notes tag ID NAME [--json]` / `notes untag ID NAME [--json]` | add / remove a tag |
| `notes archive ID [--json]` | soft-delete (still readable by id) |
| `notes versions ID [--json]` | list saved versions |
| `notes restore ID VERSION_ID [--json]` | put an earlier version's content back |
| `notes setup [--profile NAME]` | store URL and token |
| `notes version` | print the version |

`--body-file -` reads the text from stdin. `--tag` and `--task` repeat; each `--task`
adds a `- [ ] item` line to the end of the content. Tag names are resolved to ids
through the API. `append`, `prepend`, `set` and `restore` send title and content only,
never tags. If the server's versions endpoint returns no `version_id` field, `restore`
prints the versions as JSON and points you at `notes set`.

### groff notes

`notes create` can also create a note whose content is **raw groff** rather than markdown:

    notes create --title "Buttermilk pancakes" --tag recipe --format groff \
        --body-file pancakes.ms

The body is then the *source of the document*, not a description of it, and the server
derives a markdown projection for reading and for search. A note's format is fixed at
creation and never changes afterwards, so a note that will be printed has to be created
with `--format groff`; a markdown note stays markdown. `notes show --raw`, `notes edit`
and `notes set` all work on the raw source and leave the format alone. `--task` appends
markdown checkboxes, so it is refused together with `--format groff`.

The house macros, a worked recipe example and the render command live with the server, in
the Notes repository (`docs/groff-guide.md`, `groff/examples/`). Printing from inside the
app is not built yet, so rendering happens on a machine that has groff installed.

Every command that takes `--json` also takes `--json-envelope` — see *JSON output*.

## JSON output

`--json` prints the **unwrapped** payload: the `data` of the server's
`{"success": true, "data": ..., "meta"?: ...}` envelope, and nothing else. The shape is
the data shape, per command:

| command | `--json` prints |
|---|---|
| `show`, `create`, `set`, `append`, `prepend`, `restore` | the note object — **`id` at the top level**, not under `data` |
| `list`, `list --tag`, `search`, `tags`, `versions` | a bare JSON **array** |
| `tag`, `untag`, `archive` | the same rule: that endpoint's `data`; a response with no body (`archive` is a 204) prints `null` |

So the id of the note you just created is `.id`, at the top level, and a successful
write cannot be mistaken for a failed one:

    notes create --title T --body-file T.md --json | jq .id     # 127
    notes list --json | jq '.[0].id'                            # stable jq pipeline

`--json-envelope` (it implies `--json`) prints the server's response **whole** instead —
literally what the API returned, envelope and all:

    notes create --title T --body-file T.md --json-envelope | jq .data.id
    notes list --json-envelope | jq '.meta.total'

It is always the response of the request the command acts on: for `list --tag`, the
`/tags/:id/notes` page, not the `/tags` lookup that resolved the name.

Use it when you want the API's own shape (`jq .data…`), or the page metadata: `meta` — so
`meta.total` and `meta.hasMore` — is reachable **only** through this flag, because
`GET /notes` returns a page and the default output drops the wrapper. Never infer a total
from the length of the array.

Both shapes are pinned in `tests/test_json_contract.py`: the unwrapped default is a
contract, not an accident.

## Use

    notes list --tag c++          # notes carrying a tag
    notes show 98                 # by id
    notes show conformance        # by part of the title (must be unique)
    notes show 98 --raw | vim -   # content only: no headers, no decoration
    notes search "json patch"     # full-text search, ranked
    echo "- buy milk" | notes append 47 --body-file -
    notes create --title "Trip" --body-file plan.md --tag travel --task "book flights"
    notes list --json | jq '.[0].id'
    notes list --json-envelope | jq '.meta.total'   # the page metadata the default drops

`notes` does not invoke `$PAGER` for you: `notes show 98 | less` works with whatever
pager you already use.

## Tests

    ./gate.sh          # syntax + unit tests + CLI smoke, offline, no dependencies

The API is faked, so the suite needs no network and no token — and it pins the
**contract** (`/tags/:id/notes` for listing by tag, `/search?q=`, the `{success, data}`
envelope) rather than whatever the server happens to do today.

## Picking a note

    notes show            # pick from your notes, then show it
    notes edit            # pick one, then edit it
    notes show --no-pick  # never open the picker: just list what is available

`fzf` is **optional** — never a dependency. If it is installed *and* there is a
terminal, `notes show` / `notes edit` with no argument open a picker. If fzf is missing, or
the output is piped, or `$NOTES_FZF` points somewhere useless, notes prints the list, says
why it could not pick, and exits 1 without touching anything:

    fzf is not installed (or there is no terminal here), so notes cannot pick
    interactively. Install fzf for the picker, or name a note directly:
        notes show <id or part of a title>

A cancelled picker (Esc, Ctrl-C) writes nothing, which is what makes `notes edit` with no
argument safe to abort. Point notes at a specific fzf binary with `$NOTES_FZF`.

## Editing safely

    notes edit 98                          # opens $EDITOR on a temp copy
    notes edit 98 --editor "nvim -u NONE"  # a specific editor
    notes edit 98 --content-file new.md    # no editor: take the content from a file
    notes edit 98 --dry-run                # say what would be sent, send nothing

`notes edit` never clobbers. The note carries an optimistic lock — its `updated_at` —
and notes sends the value it started from. Two guards protect you:

1. before writing, notes re-reads the note; if `updated_at` moved, it **refuses**;
2. if it still loses the race, the server answers **409 Conflict** and notes refuses.

On refusal, **nothing is written** and your edited text is kept on disk, with the
exact command to retry:

    notes: note 98 changed on the server since you started — NOTHING was written.
      server now: 2026-09-16T18:23:52.418Z  (31 bytes)
      your edits: /tmp/notes-edit-98-ab12cd34/note-98.md  (30 bytes — kept)
      re-run:     notes edit 98 --content-file /tmp/notes-edit-98-ab12cd34/note-98.md

The temp file is created in a private directory (dir 700, file 600) and removed after
a successful write. If the editor exits non-zero, or deletes the file, nothing is
sent either.

Measured, and worth knowing for any other tooling: the lock field the server honours
is **`updated_at`**. Sending `updatedAt`, `contentVersion` or `version` is accepted
*and ignored* — a client that sends one of those has no protection at all and will
silently overwrite a newer note. (`DELETE /api/notes/:id` soft-deletes: 204, the note
leaves the default list but is still readable by id.)

## Licence

The Unlicense — public domain. See `LICENSE`.
