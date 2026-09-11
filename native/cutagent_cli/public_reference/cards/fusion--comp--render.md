# `fusion comp render`

Syntax: `cutagent fusion comp render [--wait]`

## Search terms

- render current Fusion comp
- calculate Fusion frames
- cache Fusion composition
- run comp Render
- render Fusion work range
- process Fusion node graph
- pre-render Fusion animation
- wait for Fusion render
- start asynchronous comp render
- evaluate Fusion frame range
- warm Fusion cache
- render active Fusion composition

## What it does

Render the composition.

## Do not use when

Use Deliver/render-job commands when the user wants an encoded timeline/movie/audio export, preset, output filename, codec, render queue, or job-status workflow.
Use `timeline frame-export`, `fusion apply --verify-frame`, or an explicit still export when the desired artifact is one PNG/JPEG for visual verification.
Use `fusion comp range START END` before render when a smaller local interval is intended; verify the range first because range accepts inverted and silently rejected bounds.
Use `fusion comp play` for interactive viewer playback rather than blocking or asynchronous graph rendering.
Do not use global `--dry-run` to estimate or preview work. It renders.

## Preflight and readback

Before rendering, establish the exact current comp, list/export its graph, and run `fusion comp current` to verify name plus ordered render/global bounds. Check MediaOut/Saver connectivity, source media, fonts, Fuses/plugins, cache paths, resolution, bit depth, frame rate, GPU/VRAM requirements, and available disk space.
For expensive graphs, narrow and verify the render range first.
After `--wait`, do not accept the success message alone. Inspect numeric comp current time/range, cache/result state, Saver outputs if configured, logs/errors, representative rendered pixels, and the DaVinci Resolve UI. Explicitly dismiss every Render-completion dialog before further automated navigation or timeline mutation.

## Public arguments and options

- `--wait` (optional, default: `false`) — Wait for render to complete

## Boundaries and gotchas

- Render range is comp-local, not timeline record-domain.
- Without `--wait`, the command returns no process/job ID, progress percentage, completion callback, status endpoint, output path, or cancellation token.
- The command does not set the render range.
- Automation must inspect the actual application UI and acknowledge each dialog before assuming DaVinci Resolve is ready for the next command.
- Global `--dry-run --wait` is mutating/work-producing.
- The command does not restore the prior comp time after render.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion comp render --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
