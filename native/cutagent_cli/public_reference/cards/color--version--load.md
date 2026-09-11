# `color version load`

Syntax: `cutagent color version load NAME [--remote] [--clip VALUE]`

## Search terms

- load color version
- switch clip grade version
- make named version current
- load remote grade version
- change active Color page version
- recall saved grading take
- switch local color version
- open previous color look
- choose clip grade branch
- activate named grade
- restore version by name

## What it does

Load a color version.

## Do not use when

Use `color version list` when only inventory is needed; load changes the active grade. Use `version duplicate`/`add` to create a new branch and `version delete` to remove one. Use `color reset` to clear the current grade rather than switch versions. Use Gallery still, DRX, PowerGrade or grade-copy/apply commands when grade data must come from another clip/artifact.
Use source-grade planning/preparation instead when one shared remote version must be coordinated across every same-source timeline cut.

## Preflight and readback

Before loading, explicitly resolve the target clip, list its local/remote versions, count exact-name matches in the intended namespace, record the current name/type, and checkpoint/export the current grade if switching away must be reversible. Confirm whether the request means local or remote; identical names can exist in both.
Confirm the list still contains the same versions, inspect nodes/grade parameters, and render/export a frame when visual output matters. Restore the original version explicitly if this was only an inspection, then save the project when the active-version choice should persist.

## Public arguments and options

- `NAME` (required) — Version name
- `--remote` (optional, default: `false`)
- `--clip` (optional)

## Boundaries and gotchas

- Exact duplicate names are fundamentally ambiguous.
- Omitting `--remote` always requests type 0.
- A local and remote `Version 1` may coexist; a name match in the wrong namespace does not satisfy the request.
- Global `--dry-run` is non-mutating but deliberately unresolved.
- Target clip resolution by name can choose the first case-insensitive filename/name match on the timeline when repeated items exist; output repeats the requested clip text rather than a canonical occurrence identity.
- Loading does not save the project.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent color version load --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
