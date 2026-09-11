# `timeline frame-export batch`

Syntax: `cutagent timeline frame-export batch --frames VALUE --out-dir VALUE [--prefix VALUE] [--extension VALUE] [--contact-sheet VALUE] [--contact-columns VALUE] [--contact-tile-width VALUE]`

## Search terms

- batch timeline frame export
- export stills at frame references
- sequential playhead sampling
- timeline contact sheet
- visual proof frames
- restore playhead after exports
- PNG JPEG timeline samples

## What it does

Export still images from the timeline.

## Do not use when

Do not use this command with an untrusted or path-like `--prefix`.
Do not expect transactional behavior. An error on a later frame or contact sheet leaves earlier frame files and any created directories in place.

## Preflight and readback

Before execution, inspect the active timeline, FPS/start/end frame, original playhead, each requested record-domain reference, output paths, existing files, available disk space, and ffmpeg availability when a contact sheet is requested. Use a simple safe prefix without separators.
Use dry-run to inspect resolved paths, sanitized frame-reference tokens, ordering, extension, and contact-sheet destination.

## Public arguments and options

- `--frames` (required) — Comma-separated timeline positions to sample
- `--out-dir` (required) — Directory for exported stills
- `--prefix` (optional, default: `"frame"`) — Output filename prefix
- `--extension` (optional, default: `"png"`) — Output extension: png|jpg|jpeg
- `--contact-sheet` (optional) — Optional contact sheet image path
- `--contact-columns` (optional, default: `3`)
- `--contact-tile-width` (optional, default: `480`) — Contact sheet tile width

## Boundaries and gotchas

- `--frames` and `--out-dir` are required options.
- At least one non-empty reference is required.
- Dry-run does not validate reference syntax against FPS or timeline start.
- Each frame is processed sequentially: set playhead, switch through the required Color page context, export, verify file presence, then continue.
- Restore failure is reported only on an otherwise successful sequence and sets recoverability to manual.
- Contact-sheet generation runs only after all frames export and the sequence restoration attempt completes.
- Tile width is not explicitly required to be positive; invalid values fail later in ffmpeg.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_TIME_REFERENCE`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline frame-export batch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
