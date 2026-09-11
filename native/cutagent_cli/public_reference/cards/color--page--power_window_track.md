# `color page power-window-track`

Syntax: `cutagent color page power-window-track [CLIP_NAME] [--shape VALUE] [--direction VALUE] [--wait-seconds VALUE]`

## Search terms

- track Power Window
- make mask follow subject
- track window backward
- bidirectional Power Window tracking
- track one frame
- motion track Color mask
- run Window tracker
- follow face with Power Window
- persist window tracking data

## What it does

Track a DaVinci Resolve Color Page Power Window.

## Do not use when

Use Magic Mask tracking for semantic subject masks.

## Preflight and readback

Save a project/grade checkpoint and fingerprint/render/matte reference. Use a wait long enough for the requested range. After success, inspect button label, before/after hashes and screenshot, then scrub the entire tracked range, inspect keyframes/matte and render locality. If the command fails after clicking, assume tracking may still have mutated the currently selected window and recover manually.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--shape` (optional, default: `"circle"`)
- `--direction` (optional) — Requested tracker direction
- `--wait-seconds` (optional, default: `2.0`) — Seconds to wait before saving and verifying tracker readback

## Boundaries and gotchas

- `--shape` is metadata only in the actual runner.
- It does not click a Window shape, confirm its type, choose a node or choose among multiple windows.
- The active grade version ID must remain identical.
- `--wait-seconds` is only a fixed sleep after button click, not a completion detector.
- Range is nominally .25..120.
- The command saves before and after; each successful save incurs a fixed five-second flush wait in addition to `--wait-seconds`.
- Project-server/cloud libraries cannot satisfy this verification route.

## Examples

- `cutagent color page power-window-track --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
