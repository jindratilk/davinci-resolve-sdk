# `media transcription`

Syntax: `cutagent media transcription --clip VALUE [--use-nested-clip-transcription]`

## Search terms

- media transcription
- Read existing DaVinci Resolve transcription for one media pool clip.
- media transcription help
- media transcription command

## What it does

Read existing DaVinci Resolve transcription for one media pool clip.

## Do not use when

Do not use to start speech recognition or when the target clip name is ambiguous.

## Preflight and readback

Identify the Media Pool clip by name and pass --clip. An empty transcript is not evidence that speech recognition has completed.

## Public arguments and options

- `--clip/-c` (required) — Clip name whose persisted transcription should be read.
- `--use-nested-clip-transcription` (optional, default: `false`) — Use nested-clip transcription when DaVinci Resolve exposes it.

## Boundaries and gotchas

- --use-nested-clip-transcription requests the nested clip's transcript where supported; it defaults to false.

## Examples

- `cutagent media transcription --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
