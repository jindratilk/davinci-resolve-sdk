# `text insert-preset`

Syntax: `cutagent text insert-preset NAME [--kind VALUE] [--text VALUE] [--fields-json VALUE] [--at VALUE] [--duration VALUE] [--track VALUE] [--name VALUE] [--allow-partial-fields] [--bold-style VALUE]`

## Search terms

- Text+ preset
- MultiText fields
- fill title text fields
- move title to video track
- basic title preset
- Fusion title preset

## What it does

Insert a DaVinci Resolve title preset.

## Do not use when

Do not guess a preset name from the GUI. Run `text list-presets`, distinguish basic titles from Fusion titles, and confirm the exact installed name.
Do not use `--allow-partial-fields` unless missing or misdirected fields are acceptable.

## Preflight and readback

Before execution, inspect available presets, the active timeline, intended record position and video track, and the preset's actual Fusion tool/input names. Use `text inspect` or Fusion tool inspection on a disposable instance when filling multiple fields.
Dry-run the exact preset, kind, timing, track, text/fields, and clip name. Remember that preview does not validate preset installation or field/tool availability.

## Public arguments and options

- `NAME` (required) — DaVinci Resolve title preset name, e.g. "Text+", "MultiText"
- `--kind` (optional, default: `"auto"`) — auto|title|fusion-title
- `--text` (optional) — Single text value to apply
- `--fields-json` (optional) — JSON object of field/tool names to text values
- `--at` (optional, default: `"0s"`) — Position (timecode/seconds/frames)
- `--duration/-d` (optional, default: `"5s"`) — Duration
- `--track` (optional, default: `1`) — Video track index
- `--name` (optional) — Timeline clip name after insertion
- `--allow-partial-fields` (optional, default: `false`) — Allow field update partial success
- `--bold-style` (optional, default: `"ExtraBold"`) — Font style for **bold** ranges

## Boundaries and gotchas

- Defaults are `--kind auto`, `--at 0s`, `--duration 5s`, `--track 1`, strict fields, and `--bold-style ExtraBold`.
- `--text` and `--fields-json` are optional; omitting both inserts the preset unchanged.
- `--text` and a non-empty `--fields-json` object are mutually exclusive.
- `--fields-json` must be a JSON object.
- Field names must be non-empty.
- Track must be at least 1.
- Dry-run validates syntax, kind, fields, positive duration, and track.
- Rename failure alone does not fail placement verification; built-in preset names may remain in readback.
- `**bold**` markers are removed from visible text and CharacterLevelStyling is attempted with `--bold-style`.
- `--allow-partial-fields` returns per-field warnings/results instead of raising; command verification status becomes partial when field results are not all okay.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent text insert-preset --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
