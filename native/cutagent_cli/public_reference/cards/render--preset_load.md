# `render preset-load`

Syntax: `cutagent render preset-load NAME`

## Search terms

- load render preset
- apply Deliver preset
- load preset by index
- render preset selector alias
- YouTube render preset
- restore saved render settings
- exact preset name
- ambiguous preset selector

## What it does

Load a render preset.

## Do not use when

Do not load a preset without first preserving current render settings if they may need to be restored.
Do not rely on a partial selector when multiple similarly named presets exist; use an exact name from `render presets`.

## Preflight and readback

Before execution, capture current render settings, mode, format/codec, output path/name, and queue. Run `render presets` and prefer the exact intended name.
Inspect the Deliver page and render a short test before treating the preset as operational.

## Public arguments and options

- `NAME` (required) — Preset name

## Boundaries and gotchas

- Match order is exact, unique case-insensitive, unique normalized, positive 1-based index, then unique normalized substring.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent render preset-load --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
