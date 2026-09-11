# `color source-grade plan`

Syntax: `cutagent color source-grade plan [--clip VALUE] [--scope VALUE] [--include-singletons]`

## Search terms

- find repeated source clips
- decide remote grade vs local grade
- group timeline cuts by source media
- plan Source Grade scope
- detect reused footage for color correction
- list same-source timeline instances
- should I use Remote Grade
- audit shared source identities
- find all cuts from one long recording
- plan one grade across multiple edits
- identify singleton vs repeated source
- inspect timeline source groups

## What it does

Plan whether color grading should use remote and source scope and local timeline scope.

## Do not use when

Use `color source-grade prepare-remote` to actually create/load a Remote Version after the plan recommends it. Use `color source-grade apply-cdl` to mutate and pixel-proof a shared CDL. Use local `color cdl`/Color page commands when the plan says timeline-local or individual cuts need trims. Use `color grade-copy` when repeated clips should start from a common grade but remain independently editable. Do not use this command to find same-source instances across other timelines or projects; it scans only the current timeline. Do not use it to verify existing Remote Version membership, active version, grade equality or pixels—none are read.

## Preflight and readback

Before planning `current-source`, identify a unique clip or put the playhead over the intended item; duplicate names can resolve the first match. Choose `timeline-sources` for a whole-timeline inventory and do not expect `--clip` to filter that scope. Afterward, inspect source identity kind/value, all instance track/ranges, group count and recommendation. For repeated groups, verify that the shared identity truly represents footage that should share a grade, then save the plan as preflight evidence before remote preparation.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--scope` (optional, default: `"current-source"`) — current-source or timeline-sources
- `--include-singletons` (optional, default: `false`) — Include one-off sources in the plan

## Boundaries and gotchas

- The same media used on another timeline is absent, even though a Remote Grade can propagate at source scope beyond what this plan proves.
- That counter sums only instances in groups whose count exceeds one.
- Supplying `--clip` with that scope does not filter the inventory.
- Only video tracks are scanned.
- Audio-only uses of the same media do not contribute to source grade recommendations.
- It is safe because the operation is read-only.
- It does not report existing Local/Remote Version names, active version types or whether a remote grade is already shared.

## Examples

- `cutagent color source-grade plan --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
