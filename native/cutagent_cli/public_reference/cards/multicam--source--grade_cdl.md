# `multicam source grade-cdl`

Syntax: `cutagent multicam source grade-cdl --angle VALUE --record-frame VALUE [--multicam-name VALUE] [--media-id VALUE] [--sequence-id VALUE] [--version-name VALUE] [--node VALUE] [--slope VALUE] [--offset VALUE] [--power VALUE] [--sat VALUE]`

## Search terms

- multicam source grade
- remote grade nested angle
- exact source CDL
- per angle grading

## What it does

Validate an unavailable multicam source CDL target.

## Preflight and readback

Use `multicam match-frame` or `multicam inspect` to confirm source identity.

## Public arguments and options

- `--angle` (required)
- `--record-frame` (required) — Frame relative to the multicam start inside the desired source item
- `--multicam-name` (optional)
- `--media-id` (optional)
- `--sequence-id` (optional)
- `--version-name` (optional, default: `"CutAgent Multicam Source Grade"`) — Remote/source grade version name
- `--node` (optional, default: `1`) — Color node index; currently node 1 only because higher nodes lack reliable CDL readback
- `--slope` (optional) — CDL slope as R G B
- `--offset` (optional) — CDL offset as R G B
- `--power` (optional) — CDL power as R G B
- `--sat` (optional) — CDL saturation

## Boundaries and gotchas

- At least one CDL field is required.
- Options are `--slope`, `--offset`, `--power`, and `--sat`.
- `--node` is one-based.
- A setter and readback on a disposable timeline instance prove only that instance, not the nested multicam source item.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent multicam source grade-cdl --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
