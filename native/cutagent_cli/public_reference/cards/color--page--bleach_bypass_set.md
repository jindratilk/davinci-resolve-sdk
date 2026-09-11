# `color page bleach-bypass-set`

Syntax: `cutagent color page bleach-bypass-set [CLIP_NAME] [--gain VALUE] [--contrast VALUE] [--desaturation VALUE] [--topology-policy VALUE]`

## Search terms

- bleach bypass look
- silver retention look
- desaturated contrast grade
- monochrome overlay branch
- RGB mixer monochrome layer
- gritty high-contrast film look
- bleach bypass intensity
- layer mixer Overlay grade

## What it does

Runs the public `color page bleach-bypass-set` CutAgent command.

## Do not use when

Use `color page rgb-mixer-set` for monochrome/channel-mixer behavior without building the Layer Mixer recipe, `color page layer-mixer-set` for an existing mixer composite mode, and normal primary/curve controls for an independently designed desaturated high-contrast grade.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--gain/--intensity` (optional) — Optional bleach bypass branch Key Output Gain, 0..1
- `--contrast` (optional) — Requested extra bleach-bypass contrast; currently returns an explicit unsupported diagnostic
- `--desaturation/--desat` (optional) — Requested extra desaturation; currently returns an explicit unsupported diagnostic
- `--topology-policy` (optional) — Requested topology policy; currently returns an explicit unsupported diagnostic

## Boundaries and gotchas

- `--gain` must be finite and within 0..1.
- Clip-name resolution is against the current timeline; duplicate names can be ambiguous and the command does not move the playhead as part of its contract.

## Stable public error codes

- `API_CALL_FAILED`
- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent color page bleach-bypass-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
