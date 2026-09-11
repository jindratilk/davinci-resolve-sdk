# `multicam angle set-enabled`

Syntax: `cutagent multicam angle set-enabled --angle VALUE --enabled [--multicam-name VALUE] [--media-id VALUE] [--sequence-id VALUE] [--media-type VALUE]`

## Search terms

- disable multicam angle
- enable multicam track
- persistent track state
- paired video audio enable

## What it does

Change whether a multicam angle is enabled.

## Do not use when

Do not remove an angle merely to hide it; disable it. Do not disable video only unless asymmetric state is deliberate. Do not leave fewer usable angles than the edit requires.

## Preflight and readback

Inspect names, states, and item counts first.

## Public arguments and options

- `--angle` (required)
- `--enabled/--disabled` (required) — Enable or disable the persistent angle track
- `--multicam-name` (optional)
- `--media-id` (optional)
- `--sequence-id` (optional)
- `--media-type` (optional, default: `"both"`) — both, video, or audio

## Boundaries and gotchas

- Choose exactly one of `--enabled` or `--disabled`.
- `--angle` is one-based.
- `--media-type` defaults to `both`.

## Examples

- `cutagent multicam angle set-enabled --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
