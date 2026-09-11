# `text insert`

Syntax: `cutagent text insert [TEXT_ARG] [--text VALUE] [--at VALUE] [--duration VALUE] [--track VALUE] [--name VALUE] [--template VALUE] [--bold-style VALUE] [--route VALUE]`

## Search terms

- add Text+ title
- Fusion setting text overlay
- styled bold text
- place title on video track
- text overlay duration
- DaVinci Resolve Text+

## What it does

Insert a styled text overlay.

## Do not use when

Do not treat a successful dry-run as proof that this restriction, the real timeline frame rate, holder availability, template import, or final placement will succeed.

## Preflight and readback

Inspect nearby timeline items and use a unique clip name for verification.
Undo or delete the inserted title manually if the result is wrong.

## Public arguments and options

- `TEXT_ARG` (optional) — Visible text to insert
- `--text` (optional) — Visible text to insert
- `--at` (optional, default: `"0s"`) — Position (timecode/seconds/frames)
- `--duration/-d` (optional, default: `"5s"`) — Duration (e.g. 5s, 120f, 00:00:05:00)
- `--track` (optional, default: `2`) — Video track index
- `--name` (optional, default: `"Text Overlay"`) — Timeline clip name
- `--template/-t` (optional) — Optional Text+ .setting template
- `--bold-style` (optional, default: `"ExtraBold"`) — Font style for **bold** ranges
- `--route` (optional, default: `"auto"`)

## Boundaries and gotchas

- Text can be supplied positionally or with `--text`.
- If both are present, `--text` silently takes precedence over the positional value.
- Empty or whitespace-only effective text is rejected.
- Defaults are `--at 0s`, `--duration 5s`, `--track 2`, `--name "Text Overlay"`, `--bold-style ExtraBold`, and `--route auto`.
- Track must be an integer of at least 1 for the setting route.
- Dry-run does not render or parse bold styling, inspect template placeholders, connect to DaVinci Resolve, inspect tracks, or verify placement.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent text insert --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
