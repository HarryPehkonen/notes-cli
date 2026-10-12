notes(1)

# NAME

notes - command-line client for a Notes server

# SYNOPSIS

*notes* [options] command [arguments]

# DESCRIPTION

*notes* reads, searches, edits, creates, tags and archives notes on any
Notes-compatible server. Python standard library only - no dependencies, one
executable file.

Configuration lives in _~/.config/notes-cli/auth.json_, created by *notes
setup*. A second server can be used via a profile: *notes --profile work list*
reads _auth.work.json_.

# COMMANDS

*setup*
	Store the server URL and API token. The token is prompted for hidden, so
	it never reaches shell history.

*list*, *ls*
	List notes, pinned first.

*show* [<id>], *get* [<id>]
	Show one note; with no argument, pick one interactively.

*search* <query>
	Full-text search. Bare words match text or tags; a _#tag_ term is a strict
	tag filter.

*create* <title> [body...]
	Create a note. Content is read from the editor ($EDITOR, $VISUAL or
	$HN_EDITOR) or given inline.

*edit* <id>
	Edit a note's content in the editor; never clobbers.

*append* <id> <text...>, *prepend* <id> <text...>
	Add text to the end or beginning of a note.

*set* <id> [<text...>]
	Replace a note's title and/or content.

*tag* <id> <name>, *untag* <id> <name>
	Add or remove a tag.

*archive* <id>
	Archive (soft-delete) a note.

*versions* <id>
	List a note's saved versions.

*restore* <id> [<version>]
	Restore a note's content from a saved version.

*tags*
	List tags with note counts.

*version*
	Print the client version.

# OPTIONS

*--profile* <name>
	Use _~/.config/notes-cli/auth.<name>.json_ instead of _auth.json_.

*--help*
	Print usage and exit.

# ENVIRONMENT

*$EDITOR*, *$VISUAL*, *$HN_EDITOR*
	Editor used by *create* and *edit*.

# SEE ALSO

The full README: https://github.com/HarryPehkonen/notes-cli

# AUTHORS

Harri Pehkonen <harry.pehkonen@gmail.com>
