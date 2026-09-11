# `color page still-match`

Syntax: `cutagent color page still-match [TARGET_CLIP] [--still VALUE] [--mode VALUE]`

## Search terms

- compare current grade to a Gallery still
- show a reference still beside the clip
- turn on Gallery image wipe
- split screen against a still
- side by side still comparison
- wipe between current frame and reference
- inspect grade against saved still
- compare look without applying still grade
- Color page reference viewer
- visual still match review

## What it does

Run Gallery still comparison through the custom edit-owned interface.

## Do not use when

Use `color gallery still apply` when the requested action is to copy a saved still's grade onto a clip; `still-match` only changes the viewer. Use Gallery `still list` first when the album/label/index is unknown, and Gallery album switching commands when the reference lives outside the current album—`still-match` has no `--album` option. Use frame export plus an image-diff workflow when reproducible pixel evidence is needed; the proof here is only a screen capture of GUI state.

## Preflight and readback

Keep the desired thumbnail visible without scrolling. Confirm the process that launches CutAgent CLI has both macOS Accessibility and Screen Recording permissions and that the largest DaVinci Resolve window uses the expected single-monitor geometry. A dry-run validates whitespace and mode aliases but does not connect, enumerate the album, find controls, check permissions, calculate coordinates, or prove the named clip is current.
Turn Image Wipe/Split Screen off and restore the previous page/still selection manually if the comparison was temporary; the command has no restoration phase.

## Public arguments and options

- `TARGET_CLIP` (optional) — Target clip name; defaults to current Color page clip
- `--still` (optional) — Requested Gallery still selector
- `--mode` (optional, default: `"side-by-side"`) — Requested viewer match mode

## Boundaries and gotchas

- Empty labels cannot be selected by label, so use their index.
- The route does not inspect thumbnail Accessibility elements or verify which still became selected after the mouse click; it immediately reports `selected: true` if the click was posted.
- The Gallery panel must already be open; the command does not click the Gallery checkbox to expose it.
- The code does not inspect screenshot pixels, thumbnail highlight, wipe divider, reference image identity, target clip identity or viewer contents.
- This route is macOS-only and needs Accessibility plus Screen Recording for the launching process.
- Permissions granted to another terminal/app do not imply the current launcher is authorized.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page still-match --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
