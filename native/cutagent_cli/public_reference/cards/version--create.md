# `version create`

Syntax: `cutagent version create [--label VALUE] [--kind VALUE] [--session-id VALUE] [--prompt-event-id VALUE] [--parent-id VALUE]`

## Search terms

- create project checkpoint
- before prompt checkpoint
- after prompt checkpoint
- manual commit version

## What it does

Create a project checkpoint.

## Do not use when

Do not use this for Blackmagic Cloud or Project Server projects; only local Disk project libraries are supported.
Do not treat it as a media archive or project archive.

## Public arguments and options

- `--label` (optional, default: `""`) — Human label for this checkpoint
- `--kind` (optional, default: `"manual_commit"`) — Checkpoint kind: before_prompt|after_prompt|manual_commit
- `--session-id` (optional) — CutAgent session id
- `--prompt-event-id` (optional) — CutAgent prompt event id
- `--parent-id` (optional) — Optional parent checkpoint id

## Boundaries and gotchas

- Kind is whitespace-trimmed but case-sensitive.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent version create --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
