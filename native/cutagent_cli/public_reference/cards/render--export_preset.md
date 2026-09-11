# `render export-preset`

Syntax: `cutagent render export-preset NAME PATH`

## Search terms

- export render preset
- render preset drpx bundle
- preset XML template
- export custom Deliver preset
- inspect render preset XML
- preset selector alias

## What it does

Export a render preset.

## Do not use when

Existing directories are allowed and no emptiness check is performed.
Do not use a built-in preset when DaVinci Resolve refuses to export it; save an equivalent custom preset first.
Do not import a modified copy under the original XML filename if a preset of that name already exists; rename the XML file to the intended new preset name first.

## Preflight and readback

Do not rely only on `exported:true` or `exists:true`.

## Public arguments and options

- `NAME` (required) — Preset name.
- `PATH` (required) — Output `.drpx` bundle path.

## Boundaries and gotchas

- Selection order is exact name, unique case-insensitive name, unique punctuation-insensitive normalized name, 1-based numeric index, then unique normalized substring.
- Ambiguous selectors fail with matches and available presets.
- It does not verify that XML exists, is newly written, matches the selected preset, or is importable.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent render export-preset --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
