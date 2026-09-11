# `edit from-edl`

Syntax: `cutagent edit from-edl PATH`

## Search terms

- import EDL as timeline
- assemble edit decision list
- create timeline from CMX 3600
- conform cuts from EDL
- rebuild timeline from EDL
- open exported EDL in DaVinci Resolve
- import selects edit list
- create cut sequence from edit decisions
- bring CMX edit into project
- relink EDL timeline
- make timeline from .edl file

## What it does

Import and assembled a timeline from an EDL.

## Do not use when

Use `timeline import` when importing another supported timeline interchange format or when the generic import surface is the intended contract. Use `edit ripple-delete` only when CutAgent should first rewrite an EDL to remove a time range.
Do not use this command as a media relinker. Do not use it when XML/AAF/OTIO/DRT fidelity is required for tracks, transitions, audio channels, effects or metadata beyond a basic EDL cut list.

## Preflight and readback

Before import, inspect the actual EDL text, declared frame mode/rate, reel identifiers, track codes, transition events, source/record timecodes and `FROM CLIP NAME` comments. Confirm every referenced source is available under identities DaVinci Resolve can conform, and check whether a timeline with the filename-stem name already exists. Run dry-run and compare its event count/title to an independent EDL inspection; duplicate the project before relying on automatic source import.
Afterward, confirm which new timeline became current and whether its name received a numeric suffix. List every track/item and compare exact event count, source/record ranges, track routing, transitions, audio, clip identity and online status with the EDL. Render or spot-check representative edit points. If import or verification errors, inspect the Media Pool and timeline list anyway because imported media or a partially created timeline is not rolled back.

## Public arguments and options

- `PATH` (required) — Path to EDL file

## Boundaries and gotchas

- Damaged names can survive preflight and fail or mislink only in DaVinci Resolve.
- Import options contain only `timelineName`.
- Treat dry-run as syntax/count evidence, not importability.
- Verification requires only at least one readable video or audio item, readable track counts and eventual visibility of the returned timeline name.
- Verification does not check clip online state, reel/name mapping, source/record timecodes, edit type, transition duration, audio channel layout, sequence FPS or pixel/audio output.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent edit from-edl --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
