# `clip take finalize`

Syntax: `cutagent clip take finalize [CLIP_NAME]`

## Search terms

- finalize selected take
- commit take choice
- collapse take stack
- keep current take permanently
- discard alternate takes
- bake selected alternate into clip
- finish take selection workflow
- remove take chooser after approval

## What it does

Finalize takes on a clip.

## Do not use when

Do not finalize when the user may need to switch back later; this command deliberately collapses the stack.

## Preflight and readback

List all takes, record the selected index/media/range, and obtain explicit workflow certainty that alternatives can be discarded. Render or inspect the selected source before finalizing. Afterward, require list count 0 and confirm the timeline item's name, source, record range, audio, transforms, and grade.

## Public arguments and options

- `CLIP_NAME` (optional)

## Boundaries and gotchas

- Global `--dry-run` is broken and destructive.
- Finalize acts on whichever take is selected; the command has no index option and its success output does not identify the surviving media.
- Finalization removes alternatives from this timeline item only.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent clip take finalize --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
