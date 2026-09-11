# `text inspect`

Syntax: `cutagent text inspect TARGET [--kind VALUE]`

## Search terms

- inspect text clip
- inspect Fusion setting
- inspect title preset
- Text+ tool inputs
- validate setting graph
- preset editability
- Fusion MediaOut check
- text template structure
- timeline text item readback

## What it does

Inspect a text clip, preset, and template.

## Do not use when

Do not use `--kind auto` to inspect a timeline clip; auto never selects clip mode. Pass `--kind clip` explicitly.
Do not treat local template `valid: true` as proof that DaVinci Resolve can import/render the composition.

## Preflight and readback

Before template inspection, resolve the exact trusted local file. Before clip inspection, make the intended project/timeline active and ensure the target name is unique across timeline video/audio items.
Choose `--kind template`, `clip`, or `preset` explicitly whenever target identity matters. For template output, inspect both `errors` and `warnings`, not only `valid`. For clip output, inspect the resolved item identity and field/tool list.
Treat unknown preset output as a discovery miss, not confirmation that the preset exists.

## Public arguments and options

- `TARGET` (required) — Clip/preset/template target
- `--kind` (optional, default: `"auto"`) — auto|clip|preset|template

## Boundaries and gotchas

- Exact help is `cutagent text inspect TARGET [--kind auto|clip|preset|template]`.
- The command is read-only and has no special dry-run branch.
- Tool headers must match the supported line-oriented `Name = Class {` shape.
- `valid` is exactly `not errors`; warnings do not make a template invalid.
- PolyPath points all in the 0..1 range produce a normalized-center-coordinate warning.
- Preset inspection does not prove installation or discover GUI presets.
- The target is used only as a clip name; this command exposes no track/record-frame selector.
- Matching tries exact case-sensitive candidates, then case-insensitive/basename matching.
- Duplicate clip names are not rejected; the first match wins.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent text inspect --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
