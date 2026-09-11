# `text insert-template-batch`

Syntax: `cutagent text insert-template-batch [--spec VALUE] [--spec-json VALUE]`

## Search terms

- batch captions
- bulk timed text overlays
- empty upper video track
- multiple setting templates
- Text+ seed clip
- batch lower thirds

## What it does

Insert multiple Text+ template clips from one template.

## Do not use when

Do not use a non-empty target track unless existing-item overlap and failure cleanup are explicitly acceptable. Batch overlap validation covers only planned batch items, not existing timeline items.

## Preflight and readback

Save/checkpoint the project and record the active project/timeline.
Compare all non-target tracks yourself and visually inspect representative first/middle/last items. For Fusion-holder batches, inspect every per-item verification because success remains only partial.

## Public arguments and options

- `--spec` (optional) — Path to Text+ template batch JSON spec
- `--spec-json` (optional) — Inline Text+ template batch JSON spec

## Boundaries and gotchas

- Exactly one spec input is required.
- `--spec` expands `~`, becomes absolute, and must name an existing file.
- The outer JSON must be an object.
- The template path expands `~`, becomes absolute, and must name a file.
- Every item must be an object with non-empty string `text`.
- Durations must convert to at least one frame.
- Absolute record frames must be non-negative integers.
- Existing timeline items are not included in planned-range overlap validation.
- Track must be a positive integer.
- Allowing a non-empty/lower track can collide with existing clips because only batch-to-batch overlap is checked.
- Item params use the same forms and are appended after root params, so later duplicate keys win.
- Post-reopen placement verification requires the selected track count to equal the plan and matches name/start/duration with duplicate-name counts.
- Each sampled accessible graph must contain TextPlus and MediaOut.
- Cleanup can delete only created items that were successfully rediscovered and collected.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent text insert-template-batch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
