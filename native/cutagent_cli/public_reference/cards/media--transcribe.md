# `media transcribe`

Syntax: `cutagent media transcribe [--clip VALUE] [--folder VALUE] [--language VALUE]`

## Search terms

- transcribe Media Pool clip
- speech to text source media
- analyze audio transcript
- transcribe all clips in bin
- generate DaVinci Resolve transcription
- detect spoken words in footage
- create source transcript in English
- transcribe interview media
- analyze sound descriptions

## What it does

Transcribe clip audio.

## Do not use when

Use transcript/subtitle generation or render transcript commands when a timeline subtitle track or exported transcript file is required.

## Preflight and readback

Choose a language code only when known to be supported. For speech-critical output, verify language, accuracy, speaker segmentation, and timing in DaVinci Resolve before using it downstream.

## Public arguments and options

- `--clip/-c` (optional) — Clip name to transcribe.
- `--folder/-f` (optional) — Folder path to transcribe.
- `--language/-l` (optional) — Language code.

## Boundaries and gotchas

- `--clip` and `--folder` are mutually exclusive, and unlike clear-transcription, neither may be omitted.

## Examples

- `cutagent media transcribe --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
