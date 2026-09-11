# `timeline import`

Syntax: `cutagent timeline import PATH`

## Search terms

- import timeline file
- import EDL timeline
- import FCPXML timeline
- import AAF timeline
- import OTIO timeline
- import DRT timeline
- unique imported timeline name
- set imported timeline current

## What it does

Import a timeline from file.

## Do not use when

Do not rely on `--dry-run` for safety. This command has no dry-run branch and can import a real timeline when DaVinci Resolve is connected.
Do not import an untrusted, uninspected, or ambiguously named interchange file into an important project without a checkpoint.

## Preflight and readback

Before execution, checkpoint/save the project; inspect the file's existence, size, extension, provenance, timeline name, frame rate, start timecode, media paths, tracks, transitions, effects, and expected compatibility. Record the current timeline and existing timeline names.
After execution, enumerate project timelines and confirm the imported timeline's actual name/current status, track structure, timing, media links, effects, audio mapping, and frame rate. If the command errors after import, check for a newly created timeline before retrying to avoid duplicates.

## Public arguments and options

- `PATH` (required) — Path to EDL/XML/AAF/DRT/OTIO file

## Boundaries and gotchas

- There is no command-level dry-run branch.
- With a connected project, `--dry-run` can still perform a real import.
- The command does not trim, expand `~`, absolutize, canonicalize, or preflight the path.
- It does not verify that the file exists, is readable, is non-empty, or matches its extension before connecting.
- Collision matching is case-sensitive.
- The CLI discards the returned timeline object and emits only `Imported timeline from: PATH`.
- Success output does not report the selected unique name, imported object, current-timeline readback, file format, or media-link status.
- It does not verify timeline contents, effects, media relinking, frame rate, start timecode, or pixels.
- It does not save the project automatically.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `MISSING_ARGUMENT`

## Examples

- `cutagent timeline import --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
