# `text update`

Syntax: `cutagent text update [--text VALUE] [--fields-json VALUE] [--clip VALUE] [--track VALUE] [--record-frame VALUE] [--role VALUE] [--tool VALUE] [--tool-candidate VALUE] [--input VALUE] [--uppercase] [--double-spaces] [--styled] [--bold-style VALUE] [--cls-tool VALUE] [--allow-partial-fields]`

## Search terms

- change Fusion title text
- set StyledText
- header uppercase text
- edit timeline title

## What it does

Update text in an existing Fusion and Text+ timeline item.

## Do not use when

Do not use this command until the exact target item and its Fusion text tools/inputs have been inspected.
Strict mode also is not transactional: earlier fields can remain changed when a later field fails.
Do not treat command verification as exact value or visual verification. Setter acceptance, text readback equality, CharacterLevelStyling, font availability, and rendered output are different checks.

## Preflight and readback

Before execution, make the intended project/timeline active, inspect the clip with `text inspect`, and prefer a unique name or exact video track plus record-frame point. Record current values and create a project checkpoint for important edits.
Dry-run the request, but manually validate selector exclusivity and separately record transformation/styling options omitted from preview output.
On any strict or partial failure, compare all fields and manually restore prior values.

## Public arguments and options

- `--text` (optional) — Single text value to apply
- `--fields-json` (optional) — JSON object of field/tool names to text values
- `--clip` (optional) — Clip name selector
- `--track` (optional) — Video track index selector
- `--record-frame` (optional) — Record-domain point selector
- `--role` (optional) — Optional role hint: body/header
- `--tool` (optional) — Explicit tool name
- `--tool-candidate` (optional, repeatable, default: `[]`) — Additional preferred tool names
- `--input` (optional, repeatable, default: `[]`)
- `--uppercase` (optional, default: `false`) — Uppercase final text
- `--double-spaces` (optional, default: `false`) — Replace spaces with double spaces
- `--styled/--plain` (optional, default: `false`) — Force CharacterLevelStyling parsing
- `--bold-style` (optional, default: `"ExtraBold"`) — Bold style for markdown ranges
- `--cls-tool` (optional, repeatable, default: `[]`) — Preferred CLS tool candidates
- `--allow-partial-fields` (optional, default: `false`) — Allow field update partial success

## Boundaries and gotchas

- Exactly one effective text source is required.
- `--text` and a non-empty `--fields-json` object are mutually exclusive.
- Empty/whitespace-only single text is rejected when there are no fields.
- Field JSON must be an object with non-empty keys and scalar non-null values.
- Track and record frame must be supplied together.
- Clip name cannot be combined with track/record frame.
- Track/record selection searches video items only.
- Clip-name matching scans tracks in ascending order and returns the first exact/case-insensitive/property/basename match.
- Duplicate clip names are not rejected.
- `--role` help suggests `body` or `header`, but arbitrary strings are not rejected.
- `--uppercase` and `--double-spaces` apply only when the effective role is exactly `header`.
- `--double-spaces` replaces every ordinary space with two spaces.
- An exact `--tool` is tried first.
- Repeatable `--tool-candidate` values are ordered preferences.
- Thus `--plain` cannot preserve literal paired `**` markers.
- `--styled` with no bold range does not create a style range.
- Markdown parsing removes `**` and creates style code 109 ranges using `--bold-style`.
- With multiple fields, explicit role, `--tool`, and `--tool-candidate` are not used as single-field overrides; each field derives its own semantic candidates.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent text update --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
