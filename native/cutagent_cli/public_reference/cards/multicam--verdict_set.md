# `multicam verdict-set`

Syntax: `cutagent multicam verdict-set --status VALUE [--multicam-name VALUE] [--clip-name-pattern VALUE] [--angle-count VALUE] [--label VALUE] [--verified-on VALUE] [--note VALUE] [--rule-id VALUE] [--registry-path VALUE]`

## Search terms

- record multicam UI verdict
- confirm multicam GUI family
- reject multicam UI family
- multicam clip regex rule
- multicam angle count evidence
- verified-on multicam
- manual render verification notes
- isolated verdict registry

## What it does

Update a multicam review note.

## Do not use when

It records manual evidence consumed by inspection/support classification.
Do not provide both `--multicam-name` and `--clip-name-pattern`, or neither.
Do not use a broad regex or omit `--angle-count` when evidence applies only to one structural family.
Do not reuse an existing rule ID unless replacing that rule is intentional; the complete rule is replaced, not merged.

## Preflight and readback

Use dry-run to validate status, selector, and date. Choose a stable descriptive rule ID and narrow regex/angle count. Put evidence limitations and reproduction details in repeatable notes.
Run `multicam inspect` against a matching and nonmatching family to confirm intended precedence/scope.
Preserve the registry change as reviewable evidence; do not leave experimental rules in the repository default.

## Public arguments and options

- `--status` (required) — Manual UI verdict status: ui_confirmed or ui_rejected
- `--multicam-name` (optional) — Exact multicam clip name to match
- `--clip-name-pattern` (optional) — Regex pattern used to match multicam clip names
- `--angle-count` (optional) — Optional angle count filter for the verdict rule
- `--label` (optional) — Human-readable verdict label
- `--verified-on` (optional) — Absolute verification date in YYYY-MM-DD format
- `--note` (optional, repeatable) — Repeatable note entry stored with the verdict
- `--rule-id` (optional) — Optional stable rule id to update
- `--registry-path` (optional) — Optional manual UI verdict registry path

## Boundaries and gotchas

- Exactly one of exact name or regex pattern is required.
- `--verified-on` must match `YYYY-MM-DD` and be a real calendar date.
- Dry-run validates but does not reveal default label/date/rule ID and does not write.
- Duplicate IDs already present beyond the first are not removed.

## Examples

- `cutagent multicam verdict-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
