# `fairlight adr record`

Syntax: `cutagent fairlight adr record [--cue VALUE]`

## Search terms

- record ADR cue
- punch ADR recording
- run ADR beeps and streamers
- capture another ADR take
- start Fairlight ADR session
- record selected cue
- launch ADR prompt recording

## What it does

Record the selected Fairlight ADR cue.

## Do not use when

After recording, use clip list/rename/move/gain/EQ/processing commands on the created timeline items.

## Preflight and readback

For a real session, configure and test input patching, record arm, destination, cue timing, prompt, pre/post-roll and monitoring in DaVinci Resolve itself.
After the expected unsupported response, perform the ADR take manually. Then verify that a new media/timeline audio item exists at the intended cue span, inspect A/V sync and take identity, and use supported CutAgent clip/track operations.

## Public arguments and options

- `--cue` (optional) — ADR cue identifier/name to record

## Boundaries and gotchas

- A failure is its intended and only behavior.
- `--cue` is optional free text with no existence, uniqueness or emptiness validation.
- Dry-run is not a recording plan.
- If DaVinci Resolve is already recording, this command does not detect, join or stop that recording.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight adr record --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
