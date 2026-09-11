# `timeline compound-create`

Syntax: `cutagent timeline compound-create --in VALUE --out VALUE [--track-type VALUE] [--track VALUE] [--name VALUE] [--start-tc VALUE]`

## Search terms

- create compound clip
- compound timeline items
- group clips by range
- compound selected tracks
- nested timeline clip
- combine video and audio clips
- record-domain compound range
- compound clip start timecode

## What it does

Create a compound clip from a timeline range.

## Do not use when

Do not use this command when the in/out boundaries must trim or split clips precisely. The range selects whole overlapping items; it does not blade or crop them before compounding.
Do not include `all` tracks without inspecting linked audio, subtitle items, transitions, and partially overlapping clips. Every qualifying item is handed to the compound operation.
Do not run without a checkpoint when preserving the original flat timeline structure matters.

## Preflight and readback

Before execution, inspect the active timeline, FPS/start frame, exact item bounds on every selected track, links, transitions, and intended compound name/start timecode. Create a project checkpoint.
Use dry-run to validate record references, range ordering, track type, and intended clip-info only. Manually enumerate actual overlaps because preview does not connect.

## Public arguments and options

- `--in` (required) — Record-domain in reference
- `--out` (required) — Record-domain out reference
- `--track-type` (optional, default: `"all"`) — video, audio, subtitle, all
- `--track` (optional, default: `0`) — Track index (0 = all tracks for selected type)
- `--name` (optional) — Optional compound clip name
- `--start-tc` (optional) — Optional compound clip start timecode

## Boundaries and gotchas

- Exact help is `cutagent timeline compound-create --in REF --out REF`.
- Both range options are required.
- Out must resolve strictly after in.
- The command does not trim, blade, duplicate, or constrain the item to the requested range before compounding.
- Output echoes requested range and clip info but does not compare requested name/start timecode with created readback.
- It does not re-enumerate the timeline to prove that exactly one compound replaced the inputs.
- Dry-run does not enumerate tracks/items or prove that the range selects anything.
- Dry-run includes the requested name/startTimecode and normalized track type/index.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline compound-create --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
