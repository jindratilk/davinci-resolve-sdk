# `color thumbnail`

Syntax: `cutagent color thumbnail [--output VALUE]`

## Search terms

- export current frame as image
- save frame under playhead
- Color page thumbnail
- export viewer frame PNG
- save current clip thumbnail
- capture playhead frame JPEG
- still image from current frame
- quick visual proof of grade
- export graded frame without render job
- capture current Color page result
- frame grab to file

## What it does

Export thumbnail of current clip under playhead.

## Do not use when

Use `timeline frame-export` for an explicit timecode/frame rather than the current playhead, or `timeline frame-export-batch` for several positions. Use `color gallery still grab` when the result must be a Gallery still that retains grade metadata and can later be applied, labeled, or exported. Use `color still grab-all` for one Gallery still per eligible timeline clip. Use a render command when codec, alpha, scaling, burn-ins, handles, a frame range, or repeatable Deliver settings matter; this command exports one still with no render configuration. Do not use `color thumbnail` to inspect node parameters or prove which grade controls changed—use the relevant Color/Fusion readback plus a before/after image comparison.

## Preflight and readback

Before running, inspect the current timeline, playhead timecode and video item under it; this command has no clip or timecode selector and will capture whichever visible composite DaVinci Resolve currently presents. If the file is verification evidence, export a baseline before the mutation under a distinct filename and record active color version/project color-management context.
Keep PNG for exact pixel comparisons—JPEG is lossy and this command reports no JPEG dimensions. A successful file-existence check does not by itself prove the intended clip, frame, active version or visual result was captured.

## Public arguments and options

- `--output/-o` (optional, default: `"color_thumbnail.png"`) — Output file path

## Boundaries and gotchas

- There is no `--clip`, `--track`, `--frame` or `--timecode`, so a changed playhead or higher visible track changes the captured composite without changing the invocation.
- The CLI does not restrict output to PNG/JPEG or verify that the encoded format matches the suffix beyond inspecting the resulting header.
- The command does not create a Gallery still or DRX sidecar; the exported bitmap cannot later reconstruct the grade.

## Examples

- `cutagent color thumbnail --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
