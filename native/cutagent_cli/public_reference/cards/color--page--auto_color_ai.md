# `color page auto-color-ai`

Syntax: `cutagent color page auto-color-ai [CLIP_NAME] [--undo-after-proof] [--proof-dir VALUE]`

## Search terms

- automatic color correction
- Auto Color
- AI color balance
- one-click grade
- neutralize image automatically
- fix exposure and white balance automatically
- DaVinci Resolve Color menu Auto Color
- analyze shot and apply automatic grade

## What it does

Apply DaVinci Resolve Auto Color.

## Do not use when

Use `color page shot-match-apply` when matching a target shot, `color page still-match` for a gallery-still look, or explicit `wheel-set`, `primary-set`, curve and white-balance commands when the correction must be deterministic and inspectable. Do not use this command for a non-current clip: the GUI route deliberately refuses a requested name that does not match the current Color-page clip. Do not use `--undo-after-proof` when the resulting automatic grade is intended to remain.

## Preflight and readback

Before running, put the playhead over the intended clip, verify `clip current`, ensure macOS Accessibility is granted to the process running CutAgent CLI, and preserve any unrelated pending undo history. If the command reports pixel-identical frames, inspect the clip and undo state manually before retrying on a different frame.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--undo-after-proof/--keep-applied` (optional, default: `false`)
- `--proof-dir` (optional) — Directory for before/after proof frame exports

## Boundaries and gotchas

- This is a macOS-only GUI-assisted route.
- `--undo-after-proof` is reached only after a changed-pixel proof succeeds.
- Undo verification is deliberately strict: the third frame must have zero changed pixels from the original.
- `--proof-dir` is created if absent.

## Examples

- `cutagent color page auto-color-ai --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
