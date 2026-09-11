# `text insert-template`

Syntax: `cutagent text insert-template TEMPLATE [--text VALUE] [--fields-json VALUE] [--image VALUE] [--param VALUE] [--name VALUE] [--at VALUE] [--duration VALUE] [--track VALUE] [--holder-kind VALUE] [--holder VALUE] [--style-markdown] [--bold-style VALUE] [--require-text] [--require-image] [--require-styling] [--keep-rendered] [--rendered-output VALUE]`

## Search terms

- render Text+ template
- replace setting placeholders
- custom lower third setting
- CharacterLevelStyling template
- image placeholder setting
- precise Fusion holder insertion
- rendered setting output

## What it does

Insert a Fusion title template.

## Do not use when

Templates are executable Fusion/Lua-like data, and raw replacements are inserted without Lua escaping.

## Preflight and readback

Save/checkpoint the project and inspect target-track occupancy.
Dry-run the exact render inputs with all applicable `--require-*` flags. If using `--rendered-output` or `--keep-rendered`, inspect and later remove the retained file.

## Public arguments and options

- `TEMPLATE` (required) — .setting template path
- `--text` (optional) — Text replacement for template text placeholders
- `--fields-json` (optional) — JSON object converted to template params
- `--image` (optional) — Image path replacement for image placeholders
- `--param` (optional, repeatable, default: `[]`) — Raw template replacement as KEY=VALUE; repeatable
- `--name` (optional) — Timeline clip name after insertion
- `--at` (optional, default: `"0s"`) — Position (timecode/seconds/frames)
- `--duration/-d` (optional, default: `"5s"`) — Duration
- `--track` (optional, default: `2`) — Video track index
- `--holder-kind` (optional, default: `"textplus"`) — fusion|textplus
- `--holder` (optional) — Holder preset name
- `--style-markdown/--plain-text` (optional, default: `true`) — Parse **bold** markdown into CharacterLevelStyling
- `--bold-style` (optional, default: `"ExtraBold"`) — Fusion font style for markdown bold ranges
- `--require-text` (optional, default: `false`) — Require a recognized text placeholder to be replaced
- `--require-image` (optional, default: `false`) — Require a recognized image placeholder to be replaced
- `--require-styling` (optional, default: `false`) — Require a recognized styling placeholder to be replaced
- `--keep-rendered` (optional, default: `false`) — Keep rendered temporary .setting file
- `--rendered-output` (optional) — Write rendered .setting to this path

## Boundaries and gotchas

- A custom `--holder` overrides that preset name.
- Track must be at least 1.
- Dry-run uses fixed 24 fps for its timing preview.
- Direct-import mode is selected only when text, image, effective params, require flags, and `--rendered-output` are all absent/false.
- `--keep-rendered` alone does not trigger rendering.
- Render mode checks the template path as supplied; it does not first expand `~` or normalize it to absolute.
- `--text` and `--fields-json` may be used together.
- `--fields-json` must be an object with non-empty keys and scalar non-null values.
- Repeatable `--param` values must contain a non-empty key before the first `=`.
- Field-derived params are appended after explicit `--param` entries, so a field value wins on duplicate keys.
- Placeholder matching is literal and case-sensitive.
- Default Markdown rendering removes `**` markers and inserts Font Style code 109 ranges using `--bold-style`.
- `--require-text`, `--require-image`, and `--require-styling` mean a recognized placeholder was present and replaced; they do not prove semantic validity or visible output.
- `--require-styling` can pass when an empty styling string replaced the placeholder; it does not require an actual bold range.
- Image validation checks only that the path is a file; it does not decode or validate image format.
- `--rendered-output` expands `~`, creates missing parent directories, and overwrites the destination with no overwrite confirmation.
- An explicit rendered output is always retained; cleanup does not delete it.
- If `--name` is omitted, the clip name is derived from the effective path basename.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent text insert-template --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
