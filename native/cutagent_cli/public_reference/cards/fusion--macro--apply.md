# `fusion macro apply`

Syntax: `cutagent fusion macro apply MACRO [--clip VALUE]`

## Search terms

- apply Fusion macro
- import macro setting
- apply template to clip
- macro by name
- macro .setting path
- replace clip Fusion graph
- apply lower third macro
- named clip macro import
- auto-layout macro import
- fusion.mutation macro
- macro graph readback

## What it does

Apply a Fusion macro and template to a clip.

## Do not use when

Do not use this command when a new holder clip is required.
Do not use it for placeholder rendering.
Do not use a clip name when duplicates exist or identity is uncertain. This command has no track/record-frame selector.
Export the exact clip composition and render an in-range frame.

## Preflight and readback

Before execution, confirm project, timeline, target clip name, playhead, clip range, and existing Fusion comp count.
Inspect and validate the source graph, its MediaOut, fonts, media, plugins, expressions, frame range, and layout.
Remember that dry-run does not prove the clip exists.
Inspect tool classes, SourceOp edges, text/media values, and compare a rendered in-range frame with the expected result.

## Public arguments and options

- `MACRO` (required) — Macro/template name or .setting path
- `--clip` (optional) — Clip name (or current)

## Boundaries and gotchas

- The only option is `--clip`.
- Dry-run requires the macro file to resolve but does not connect to DaVinci Resolve.
- Named-clip resolution can be ambiguous when multiple items share the same name.
- The command does not export or preserve the existing composition automatically.
- Successful import always sets verification status only to `partial`.

## Stable public error codes

- `API_CALL_FAILED`
- `MISSING_ARGUMENT`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion macro apply --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
