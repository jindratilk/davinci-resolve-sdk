# `fairlight automation list`

Syntax: `cutagent fairlight automation list [--limit VALUE] [--include-context] [--context-bytes VALUE]`

## Search terms

- fairlight automation list
- Read audio-clip volume envelopes and diagnostic mixer tokens.
- fairlight automation list help
- fairlight automation list command

## What it does

Read audio-clip volume envelopes and diagnostic mixer tokens.

## Do not use when

Do not use clip envelopes to claim Fairlight track-mixer or bus-mixer automation support. Those lanes, automation modes, pan, mute, plugin, send, EQ, and dynamics automation remain unmapped.

## Preflight and readback

Make the exact project and timeline active. If investigating a particular item, first map its track, name, unique ID, and record-frame range.

## Public arguments and options

- `--limit` (optional, default: `50`)
- `--include-context` (optional, default: `false`) — Include bounded hex/ASCII DB context around each token
- `--context-bytes` (optional, default: `32`) — Bytes before/after each token when --include-context is set

## Boundaries and gotchas

- `--include-context` can enlarge output substantially and affects only token evidence.
- The command requires an active timeline but does not save, close, or mutate the project.

## Examples

- `cutagent fairlight automation list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
