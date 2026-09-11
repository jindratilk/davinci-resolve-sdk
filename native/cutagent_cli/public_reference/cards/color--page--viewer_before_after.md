# `color page viewer-before-after`

Syntax: `cutagent color page viewer-before-after --before-at VALUE [--after-at VALUE] [--before-output VALUE] [--after-output VALUE] [--contact-sheet VALUE]`

## Search terms

- export before and after frames
- compare two timeline frames pixel by pixel
- prove a Color page image changed
- calculate changed pixel percentage
- make a before after contact sheet
- side by side rendered frame proof
- measure maximum channel difference
- locate changed image bounds
- compare reference and result frames
- verify grade output with frame diff
- save Color page proof images
- check whether two timeline positions look identical

## What it does

Export before and after Color Page frames and return pixel-diff proof metrics.

## Do not use when

Use `color page still-match` when the goal is an interactive Gallery Image Wipe/Split Screen rather than files and numeric metrics. Use `color page scope-read` for waveform/parade/histogram-style global signal measurements. Do not use two different shots or two different source frames as proof that a particular grade changed—content/motion alone can produce a full-frame diff.

## Preflight and readback

Before running, record the original playhead, confirm both requested timecodes are inside the intended timeline and identify the clip/source frame under each. If this is intended to prove a grade rather than compare shots, establish that the two positions contain genuinely comparable source pixels; ideally use the same frozen/source frame in a controlled duplicate. Choose three distinct paths whose parent directories already exist, preserve any files that must not be overwritten, and ensure ffprobe/ffmpeg are available. Dry-run is useful for path collision checks but does not parse timecodes, connect, seek, export, inspect dimensions, decode pixels or test restoration.
Review the optional contact sheet; it has no labels, so retain which side is before (left) and after (right).

## Public arguments and options

- `--before-at` (required) — Timeline position for the before/reference frame
- `--after-at` (optional) — Timeline position for the after frame; current playhead when omitted
- `--before-output` (optional, default: `"color_before.png"`) — Exported before frame path
- `--after-output` (optional, default: `"color_after.png"`) — Exported after frame path
- `--contact-sheet` (optional) — Optional side-by-side proof image path

## Boundaries and gotchas

- “Before” does not mean grade-bypassed or pre-mutation.
- It is simply the rendered frame at `--before-at` under the current project state. “After” is likewise a second current-state timeline position.
- They do not require any changed pixel.
- If `--after-at` is omitted, the after position is the original playhead captured before seeking to the before frame.
- Before, after and contact-sheet paths must be pairwise distinct after expansion and absolute resolution.
- The command does not preserve prior artifacts.
- Both decoded arrays must have identical height, width and channel shape.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page viewer-before-after --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
