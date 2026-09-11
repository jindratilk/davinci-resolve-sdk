# `multicam replace audio`

Syntax: `cutagent multicam replace audio [--multicam-name VALUE] [--media-id VALUE] [--sequence-id VALUE] [--angle VALUE] [--empty VALUE] [--offset VALUE] [--audio-offsets-json VALUE] [--unmapped VALUE] [--force]`

## Search terms

- replace multicam angle audio
- isolated microphone multicam
- empty multicam audio angle
- one-based Angle number
- multicam audio sync offset
- remove unmapped audio
- multicam audio dry-run

## What it does

Update audio items inside multicam angles.

## Do not use when

The CLI rejects that conflict.
Do not accept MediaRef-only verification as complete timing proof. Independently verify start, source-in, duration, timemap, audio channel behavior, sync, and rendered playback.

## Preflight and readback

Decide explicitly what every untargeted audio angle should do.
Run dry-run with exact media/sequence selector when possible.

## Public arguments and options

- `--multicam-name` (optional)
- `--media-id` (optional)
- `--sequence-id` (optional)
- `--angle` (optional, repeatable) — DaVinci Resolve one-based angle audio replacement: 1=/path/mic.wav
- `--empty` (optional, repeatable)
- `--offset` (optional, repeatable) — Per-angle sync offset in frames: 1=-12, 2=5
- `--audio-offsets-json` (optional) — Path to JSON offsets object; keys may be angle_1 ids or legacy source ids
- `--unmapped` (optional, default: `"keep"`) — Policy for existing audio angles not mentioned by --angle/--empty: keep, remove, or error
- `--force/-f` (optional, default: `false`)

## Boundaries and gotchas

- Accepted angle text is a positive integer or case-insensitive `Angle N`.
- Empty targets must also be unique.
- An angle cannot be both replaced and emptied.
- `--offset` uses the same one-based angle syntax and accepts negative/positive integer frames.
- Duplicate explicit offset targets are rejected.
- Audio offsets JSON must exist, parse as an object/`offsets` object, and have integer values.
- No overlap/empty post-clip range is a validation error.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent multicam replace audio --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
