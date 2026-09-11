# `fusion text set`

Syntax: `cutagent fusion text set --text VALUE [--clip VALUE] [--track VALUE] [--record-frame VALUE] [--role VALUE] [--tool VALUE] [--tool-candidate VALUE] [--input VALUE] [--uppercase] [--double-spaces] [--styled] [--bold-style VALUE] [--cls-tool VALUE]`

## Search terms

- set Fusion TextPlus text
- CharacterLevelStyling text
- uppercase header text
- double-space Fusion title
- verify TextPlus readback

## What it does

Update Fusion text.

## Do not use when

Do not assume `--tool` is a strict fail-closed selector.
Both are required together; `--clip` is mutually exclusive with the pair.
Do not trust dry-run to validate selectors, clip existence, composition availability, tools, inputs, or write/readback behavior.
Do not assume styled text was fully applied from clean text success.

## Preflight and readback

Record the exact original text and styling as an inverse command. Prefer explicit `--clip`, `--tool`, and `--input` values; still treat the returned selected tool as authoritative.

## Public arguments and options

- `--text` (required) — Text to set
- `--clip` (optional) — Clip name selector
- `--track` (optional) — Video track index selector
- `--record-frame` (optional) — Record-domain point selector
- `--role` (optional) — Optional role hint: body/header
- `--tool` (optional) — Explicit tool name
- `--tool-candidate` (optional, repeatable) — Additional preferred tool names
- `--input` (optional, repeatable)
- `--uppercase` (optional, default: `false`) — Uppercase the final text
- `--double-spaces` (optional, default: `false`) — Replace spaces with double spaces
- `--styled/--plain` (optional, default: `false`) — Force CharacterLevelStyling parsing
- `--bold-style` (optional, default: `"ExtraBold"`) — Bold style name for CharacterLevelStyling
- `--cls-tool` (optional, repeatable) — Preferred CLS tool candidates

## Boundaries and gotchas

- Required option is `--text TEXT`.
- Selectors are `--clip TEXT` or paired `--track INTEGER --record-frame TEXT`.
- Text selection options are `--role`, `--tool`, repeatable `--tool-candidate`, and repeatable `--input`.
- Styling options are `--uppercase`, `--double-spaces`, `--styled/--plain`, `--bold-style`, and repeatable `--cls-tool`.
- Help reports `--plain` as the default side of the styled flag.
- Clip plus track/record pair is rejected as mutually exclusive.
- The selected timeline item must already contain a Fusion composition.
- Header uppercase/double spacing apply only when `role == "header"`; the flags are ineffective for other roles.
- Text with `**` markers triggers styled parsing even when `--plain` is in effect.
- Styled readback contains CLS tool/text/value only when one was found.
- Dry-run normalized `hello **bold** world` as `HELLO BOLD WORLD`, counted one styled range, and left actual text empty.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fusion text set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
