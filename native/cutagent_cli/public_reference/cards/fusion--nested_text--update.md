# `fusion nested-text update`

Syntax: `cutagent fusion nested-text update [--header VALUE] [--body VALUE] [--clip VALUE] [--track VALUE] [--record-frame VALUE] [--header-clip VALUE] [--body-clip VALUE] [--header-uppercase] [--header-double-spaces] [--preset VALUE] [--bold-style VALUE]`

## Search terms

- edit compound clip header body
- open nested timeline text
- legacy explanation text preset
- restore original timeline
- nested header body selector
- compound timeline dry-run
- nested text readback

## What it does

Update nested Fusion text.

## Do not use when

Do not assume dry-run is disconnected.
Do not run it on an ordinary media clip.
Do not omit explicit nested item names when item order is not a safe header/body contract.
Do not run without preserving the original timeline and existing header/body text.
Do not use `legacy-explanation` for arbitrary templates; it encodes product-specific default clip names and typography transforms.

## Preflight and readback

Before execution, inspect the outer timeline, exact compound target, backing Media Pool item, nested timeline, video-track items, and each candidate's Fusion text tools/readback.
Record the original current timeline and original header/body strings. Use explicit `--header-clip` and `--body-clip` when possible.
Run dry-run knowing it still accesses DaVinci Resolve and temporarily opens the nested context.
For visible text, export/render the nested result. To roll back, rerun the command with the captured original strings and verify both nested readbacks plus the restored outer timeline.

## Public arguments and options

- `--header` (optional) — Header text
- `--body` (optional) — Body text
- `--clip` (optional) — Compound clip name selector
- `--track` (optional) — Video track index selector
- `--record-frame` (optional) — Record-domain point selector
- `--header-clip` (optional) — Nested header clip name
- `--body-clip` (optional) — Nested body clip name
- `--header-uppercase` (optional, default: `false`) — Uppercase header text
- `--header-double-spaces` (optional, default: `false`) — Double-space header text
- `--preset` (optional) — Optional compatibility preset; legacy-explanation selects legacy explanation header/body clips and typography
- `--bold-style` (optional, default: `"ExtraBold"`) — Bold style name for CharacterLevelStyling

## Boundaries and gotchas

- No option is syntactically required.
- Text options are `--header` and `--body`.
- Outer selectors are `--clip`, `--track`, and `--record-frame`.
- Nested selectors are `--header-clip` and `--body-clip`.
- Header transforms are `--header-uppercase` and `--header-double-spaces`.
- Compatibility/style options are `--preset` and `--bold-style`.
- The command connects before its dry-run branch.
- Track and record frame must be supplied together; clip cannot be combined with them.
- The target must have a Media Pool item.
- Header uppercase/double-space transforms apply only to the header role.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion nested-text update --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
