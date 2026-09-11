# `fairlight effect list`

Syntax: `cutagent fairlight effect list [--track VALUE] [--clip VALUE] [--bus VALUE]`

## Search terms

- list effects on audio clip
- show Fairlight clip FX chain
- check whether clip has Voice Isolation
- find Gain plugin on clip
- see applied audio plugins
- list BMD effects on timeline item
- check clip audio processing
- identify first clip's Fairlight effects
- verify effect add or remove

## What it does

List Fairlight clip FX.

## Do not use when

Use `fairlight effect params EFFECT --clip NAME` when the decision requires one effect's parameters. Use `fairlight effect plugin-catalog` to discover locally available plugins, not applied ones.

## Preflight and readback

Confirm the active project/timeline and use a unique clip name. Save the project first if effects were changed manually in the GUI and disk freshness matters.

## Public arguments and options

- `--track/-t` (optional) — Audio track index to target
- `--clip` (optional) — Timeline clip name to target
- `--bus` (optional) — Bus name to target

## Boundaries and gotchas

- Omitting `--clip` silently chooses the first audio clip.
- That is useful only when the timeline and ordering are already known; on a real edit it can inspect the wrong item without an error.
- A missing or ambiguous clip produces a validation/readiness error instead.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight effect list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
