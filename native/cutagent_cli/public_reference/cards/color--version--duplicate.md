# `color version duplicate`

Syntax: `cutagent color version duplicate NAME [--remote] [--clip VALUE]`

## Search terms

- duplicate color version
- copy current grade to new version
- branch current color grade
- create alternate grading take
- save current look as named version
- clone local grade version
- make remote version from current grade
- preserve grade before experimenting
- fork clip color correction
- create another Color page version
- duplicate current look

## What it does

Duplicate a color version.

## Do not use when

Use `color version delete` to remove versions and `version list` to inventory names.
Do not use this for copying a grade to a different timeline clip: use grade-copy/apply, Gallery still, DRX, or PowerGrade commands that name both source artifact and destination. Do not use one remote duplicate as proof that every repeated cut from the source has been switched consistently; use `color source-grade plan` and `color source-grade prepare-remote` for coordinated same-source instances. Use a project checkpoint/export rather than a color version when recovery must survive deletion of the clip or project corruption.

## Preflight and readback

Before duplicating, resolve the target clip, put its intended source version/current grade active, inspect its node/grade state, and list both local and remote names at the target playhead. Decide explicitly whether the new branch must be local to this timeline item or remote/source-linked. Save or checkpoint first if grade recovery matters outside the current project state.
Afterward, run `color version list` at the target clip and confirm one new row in the intended namespace. Because the command makes the new version active, inspect its nodes/parameters and export/render a frame when actual grade equivalence matters. Keep the duplicate active for editing or restore the prior version explicitly, then save the project.

## Public arguments and options

- `NAME` (required) — New duplicate version name
- `--remote` (optional, default: `false`)
- `--clip` (optional)

## Boundaries and gotchas

- Duplicate names make later name-only activation ambiguous and make `version delete` remove every exact-name occurrence.
- `--remote` does not mean “copy this version to every repeated clip.” It creates a type-1 remote version through the selected timeline item.
- Global `--dry-run` is genuinely non-mutating here, unlike `version add` and `version delete`.
- Name and `--clip` are stripped at both ends.
- `version list` must be interpreted together with its `type` field.
- Creating a remote duplicate from a currently active local version switches the item into the new remote version.
- This command has no `--from-version`; activate the intended source version first.

## Examples

- `cutagent color version duplicate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
