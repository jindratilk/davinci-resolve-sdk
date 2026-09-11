# `fairlight send list`

Syntax: `cutagent fairlight send list [--limit VALUE] [--include-context] [--context-bytes VALUE]`

## Search terms

- inspect Fairlight sends
- list aux send tokens
- find possible send buses
- discover reverb send destination
- list candidate bus destinations
- find pre-fader send token
- find post-fader send token
- inspect SendLevel storage evidence
- check whether timeline mixer has send tokens
- diagnose unavailable Fairlight send routing

## What it does

Runs the public `fairlight send list` CutAgent command.

## Do not use when

Do not use candidate destinations as an actual send list. Use DaVinci Resolve's Fairlight mixer to inspect each track/bus send slot when the routing must be known.
Do not use `found:false` as proof that no sends exist.

## Preflight and readback

Before reading, save the intended local Disk project, confirm the active timeline name, and list tracks/buses in DaVinci Resolve. Choose `--include-context` only when raw mapping evidence is useful.
If the GUI was changed immediately beforehand, save and rerun to refresh disk consistency.

## Public arguments and options

- `--limit` (optional, default: `50`) — Maximum send-related token candidates to return
- `--include-context` (optional, default: `false`) — Include bounded hex/ASCII DB context around send and bus label tokens
- `--context-bytes` (optional, default: `32`) — Bytes before/after each token when --include-context is set

## Boundaries and gotchas

- Bus labels alone do not imply active sends.
- Binary-only state and other string encodings are invisible.
- `--limit` applies to deduplicated send tokens only.
- `truncated` refers only to send-token candidates before slicing.
- Nearby bytes must not be patched by inference.
- `--context-bytes` accepts 0 through 256.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight send list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
