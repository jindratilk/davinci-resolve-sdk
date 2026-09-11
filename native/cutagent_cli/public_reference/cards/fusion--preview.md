# `fusion preview`

Syntax: `cutagent fusion preview TEXT [--bold-style VALUE]`

## Search terms

- preview Fusion styled text
- CharacterLevelStyling preview
- parse double asterisk bold
- Fusion font style ranges
- preview ExtraBold markers
- styled text clean text
- CLS code 109 Fusion
- bold range indexes
- unmatched bold marker
- empty bold range
- Unicode styling index
- bold style Lua escaping

## What it does

Preview styled Fusion text.

## Do not use when

Do not use this as proof that text renders correctly in DaVinci Resolve.
Do not use malformed or unbalanced `**` syntax expecting validation. An unmatched opening marker silently styles the remainder of the text.
Do not use empty `****` markers. They produce a zero-length CLS entry rather than no entry.
Do not pass quotes, backslashes, or newlines in `--bold-style` unless downstream escaping is handled separately. The style value is interpolated directly into a quoted Lua fragment.

## Preflight and readback

Quote the text argument so spaces and `**` reach the CLI unchanged. Quote custom style names as a single shell argument.
Run once without global dry-run; it is already non-mutating.
Confirm ranges refer to the marker-free string and that each intended bold segment has non-zero length.
Check custom style output for valid Lua quoting.
No cleanup is normally needed.

## Public arguments and options

- `TEXT` (required) — Text with **bold** markers (e.g., "This is **important**")
- `--bold-style` (optional, default: `"ExtraBold"`) — Font style for bold text

## Boundaries and gotchas

- The command does not prove that DaVinci Resolve uses the same Unicode index domain.
- Text content is not Lua-escaped here because this command only returns clean text separately; escaping happens later in template rendering.
- It does not validate whether ExtraBold, Black, or a custom style exists for the chosen font.
- It only generates code 109 Font Style ranges; no font family, size, color, tracking, baseline, or other CLS properties.

## Stable public error codes

- `AUTH_REQUIRED`

## Examples

- `cutagent fusion preview --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
