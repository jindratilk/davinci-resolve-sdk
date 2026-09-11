# `fairlight bus list`

Syntax: `cutagent fairlight bus list [--include-context] [--context-bytes VALUE]`

## Search terms

- list Fairlight buses
- show Main and Bus labels
- enumerate timeline output labels
- check Main output model
- inspect bus binary context
- discover Fairlight bus names
- Fairlight routing label evidence

## What it does

Runs the public `fairlight bus list` CutAgent command.

## Do not use when

Do not use label presence as proof that a bus is active, assigned, audible or routed from a particular track.
Use `fairlight send list` for send/aux token candidates and track/bus state readers for actual supported mixer state.
Do not use this command to create, rename, delete or configure buses. Do not expose hex context as a user-facing routing explanation; it is forensic encoding evidence.

## Preflight and readback

Before reading, make the exact project timeline active and identify whether the question is about a label or real routing/state. Run without context first.
No post-mutation verification is required because nothing is written.

## Public arguments and options

- `--include-context` (optional, default: `false`) — Include bounded hex/ASCII DB context around bus label tokens
- `--context-bytes` (optional, default: `32`) — Bytes before/after each token when --include-context is set

## Boundaries and gotchas

- The scope is labels only.
- Bus numbers must begin 1..9 and contain at most three digits.
- `Bus 0` and `Bus 1000` do not match.
- This rejects many incidental substrings but does not prove the token's semantic role.
- Duplicate labels are collapsed by `(kind,name)` and only the first offset is retained.
- Unlike the automation token scanner, this command does not report occurrence count or all offsets.
- Context therefore covers only the first retained occurrence of each label.
- A declared-length match validates string framing only, not routing semantics.
- `--context-bytes` is accepted from 0 through 256.
- There is no `--timeline` selector.
- Dry-run never connects, decodes the model or predicts labels/counts.
- It only echoes context settings and scope.

## Examples

- `cutagent fairlight bus list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
