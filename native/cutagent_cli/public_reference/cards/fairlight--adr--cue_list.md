# `fairlight adr cue-list`

Syntax: `cutagent fairlight adr cue-list`

## Search terms

- list ADR cues
- show ADR cue sheet
- get ADR prompts
- inspect ADR takes
- export ADR cues
- list looping session cues
- retrieve ADR take metadata

## What it does

Check Fairlight ADR cue list availability.

## Do not use when

Use manual Fairlight ADR panel/cue-sheet export when actual cue names, prompts, actors, time ranges, take ratings or take selection are required. Use ordinary Fairlight clip commands after ADR audio has already been recorded into the timeline.

## Preflight and readback

If the user needs real data, identify the active local Disk project and plan `fairlight adr info --limit N` plus manual ADR-panel inspection/export.
Never claim “there are no cues” from this sentinel alone.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- If a future DaVinci Resolve release exposes ADR getters, this command will still fail until CutAgent CLI implements and verifies a real route; it does not dynamically negotiate new methods.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight adr cue-list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
