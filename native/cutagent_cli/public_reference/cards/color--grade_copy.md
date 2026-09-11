# `color grade-copy`

Syntax: `cutagent color grade-copy --from VALUE --to VALUE`

## Search terms

- copy grade between clips
- paste color correction to shots
- match target clips to source grade
- duplicate full Color page grade
- copy node grade to multiple timeline items
- batch paste grade by clip name
- transfer local grade in Disk project

## What it does

Copy grade from one clip to others.

## Do not use when

Use `color grade-apply` when transferring a DRX across projects or machines, gallery still apply for a selected gallery look, and `color cdl` for a deliberate numeric primary adjustment. Do not use name-only selection where repeated clip names make the intended timeline instances ambiguous—create unique names or use a command with record/track targeting.

## Preflight and readback

Before mutation, inspect the source grade and all target clips, confirm the active versions are local, preserve target grades as versions/DRX, and run dry-run to review the parsed target-name list. Then render representative target frames because this command performs no pixel proof and external LUT/DCTL/OpenFX dependencies may differ.

## Public arguments and options

- `--from` (required) — Source clip name
- `--to` (required) — Target clip names (comma-separated)

## Boundaries and gotchas

- Dry-run does not resolve source/targets or verify that the source has a grade.
- It restores the active timeline after reopen, but the output does not promise restoration of every UI selection/page/playhead detail.

## Examples

- `cutagent color grade-copy --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
