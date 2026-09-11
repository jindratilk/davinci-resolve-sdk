# `color page bleach-bypass-intensity-set`

Syntax: `cutagent color page bleach-bypass-intensity-set [CLIP_NAME] --gain VALUE`

## Search terms

- adjust bleach bypass strength
- bleach bypass intensity
- fade bleach bypass look
- reduce silver-retention effect
- set bleach bypass opacity
- Key Output Gain bleach bypass
- blend monochrome Overlay branch
- make bleach bypass subtler

## What it does

Runs the public `color page bleach-bypass-intensity-set` CutAgent command.

## Do not use when

Use `color page bleach-bypass-set` without `--gain` to create the fixed recipe at its default strength, or with `--gain` when creation and strength should be expressed in one invocation.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--gain/--intensity` (required) — Bleach bypass branch Key Output Gain, 0..1

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page bleach-bypass-intensity-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
