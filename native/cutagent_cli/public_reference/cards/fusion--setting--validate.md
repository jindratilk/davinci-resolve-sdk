# `fusion setting validate`

Syntax: `cutagent fusion setting validate PATH [--fail-on-warning] [--runtime] [--holder-kind VALUE] [--holder VALUE] [--at VALUE] [--duration VALUE] [--text VALUE] [--image VALUE] [--style-markdown] [--bold-style VALUE] [--param VALUE] [--require-text] [--require-image] [--require-styling] [--cleanup]`

## Search terms

- validate Fusion setting
- static setting validation
- scratch timeline import
- Fusion node diagnostics
- setting fail on warning
- Fusion import verification
- temporary validation clip
- validate Text+ template
- MediaOut structural validation
- setting cleanup failure
- DaVinci Resolve setting smoke

## What it does

Validate a Fusion template.

## Do not use when

Do not claim visible output from this command.
Isolation deliberately avoids touching it.

## Preflight and readback

Resolve paths and template dependencies, then run `fusion setting inspect` or `fusion setting summary` to understand expected tools, warnings, and layout.
Use the default `--cleanup` and a short duration unless retention is explicitly required.
If the input is a template, provide text, image, styling mode, repeatable parameters, and relevant `--require-*` flags so the imported file represents the intended rendered graph.
Independently list timelines and re-check the original timeline/tool graph after cleanup. Export frames separately if the setting must produce visible pixels.
If cleanup or restore is incomplete, stop and remove the exact named scratch timeline only after confirming it is the validator-created object.

## Public arguments and options

- `PATH` (required) — .setting file to validate
- `--fail-on-warning` (optional, default: `false`) — Return VALIDATION_ERROR when warnings are present
- `--runtime` (optional, default: `false`) — Import into an isolated scratch timeline holder and inspect runtime tool diagnostics
- `--holder-kind` (optional, default: `"fusion"`) — Runtime validation holder kind: fusion or textplus
- `--holder` (optional) — Runtime validation holder name
- `--at` (optional, default: `"0s"`) — Runtime validation timeline position
- `--duration` (optional, default: `"2s"`) — Runtime validation temporary clip duration
- `--text` (optional) — Render template text before runtime validation
- `--image` (optional) — Render template image path before runtime validation
- `--style-markdown/--plain-text` (optional, default: `true`) — Parse **bold** markdown before runtime validation
- `--bold-style` (optional, default: `"ExtraBold"`) — Fusion font style used for markdown bold ranges
- `--param` (optional, repeatable, default: `[]`) — Raw template replacement as KEY=VALUE; repeatable
- `--require-text` (optional, default: `false`) — Require a recognized text placeholder before runtime validation
- `--require-image` (optional, default: `false`) — Require a recognized image placeholder before runtime validation
- `--require-styling` (optional, default: `false`) — Require a recognized styling placeholder before runtime validation
- `--cleanup/--keep-temporary-clip` (optional, default: `true`) — Delete the temporary runtime validation scratch timeline

## Boundaries and gotchas

- Static mode does not contact DaVinci Resolve.
- Static success returns `valid:true` but explicitly does not verify rendering, timeline import, node status, probes, or pixels.
- An unresolved placeholder can remain structurally valid; static validation does not understand business-level template completeness.
- `--holder-kind` accepts only `fusion` or `textplus`.
- `--keep-temporary-clip` sets cleanup false and retains the scratch timeline; the option name is narrower than its actual effect.

## Stable public error codes

- `RESOLVE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion setting validate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
