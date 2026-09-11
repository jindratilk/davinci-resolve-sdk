# `color version add`

Syntax: `cutagent color version add NAME_OR_CLIP [MAYBE_NAME] [--remote] [--clip VALUE]`

## Search terms

- add color version
- create alternate grade version
- new local Color page version
- create remote grade version
- make another grading take
- save current look as new version
- add clip grade variation
- create named color version
- new remote version for source
- branch a grade
- create Color page version by name
- add version to current clip

## What it does

Add a new color version.

## Do not use when

Use `color version duplicate` when the desired contract is explicitly “duplicate the current grade” with before/after listing and active-version verification; add delegates initialization entirely to DaVinci Resolve and returns only a message. Use `version activate/load` to switch to an existing version, `version delete` to remove one, and `version list` before creation to prevent name collisions. Use `color source-grade prepare-remote` when the same named remote version must be coordinated across all same-source timeline instances. Use Gallery still/DRX/grade-copy commands when the version must receive grade content from a different clip or artifact.

## Preflight and readback

Before running, explicitly resolve the target clip, list local and remote versions, record current name/type and inspect the current grade that DaVinci Resolve will use as creation context. Choose a name unique within the requested type and across the other type when human/agent ambiguity matters. Save/checkpoint the project if the current grade must be recoverable.
Afterward, immediately list versions and confirm exactly one new row of the intended type. Inspect/render the new version's grade rather than assuming contents from the success message. Restore the intended active version and save the project explicitly.

## Public arguments and options

- `NAME_OR_CLIP` (required) — Version name (or clip name in legacy syntax)
- `MAYBE_NAME` (optional) — Version name in legacy syntax: color version add <clip> <name>
- `--remote` (optional, default: `false`)
- `--clip` (optional)

## Boundaries and gotchas

- Duplicate names are allowed.
- Output is only `{message}`.
- A missing/extra positional can therefore target or name something different than intended; prefer explicit `--clip`.

## Examples

- `cutagent color version add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
