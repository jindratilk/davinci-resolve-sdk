# `color source-grade prepare-remote`

Syntax: `cutagent color source-grade prepare-remote NAME [--clip VALUE] [--create] [--load] [--include-singletons]`

## Search terms

- create Remote Color Version
- load shared source grade on all cuts
- prepare DaVinci Resolve Remote Grade
- switch same-source clips to remote version
- make one grade version shared by source
- activate remote grade across timeline instances
- set up source-level color grading
- create named remote version
- load existing remote version everywhere
- prepare repeated clips for one shared grade
- verify Remote Version propagation
- initialize source grade workflow

## What it does

Create and load one shared remote grade version for all timeline cuts from the same source media.

## Do not use when

Use `color source-grade plan` before this command when source grouping/scope has not been reviewed. Use ordinary local Color Versions/grades when cuts should remain independently graded or the source is a one-off. Use `--no-create` when absence must fail rather than silently create a new shared version, and `--no-load` when the current version selections must remain unchanged. Do not use this output as evidence that a look exists or propagated; it validates version visibility/selection only. Do not expect it to find/prove same-source clips on other timelines.

## Preflight and readback

Before running, inspect `source-grade plan`, list existing local/remote version names, record the active version on every matching cut, and confirm exact source identities/tracks/ranges. Choose a unique name or explicitly accept loading an existing shared grade; name reuse does not create a checkpoint. For singletons, leave the default guard unless remote scope is intentionally desired. Decide independently whether create and load should be enabled.
Apply/read/render the actual grade next. Check other timelines that use the source because this command only enumerates the active timeline. If any instance fails, inspect all earlier instances: create/load operations are incremental and not rolled back, so partial active-version changes can remain.

## Public arguments and options

- `NAME` (required) — Remote version name to create/load
- `--clip` (optional) — Clip name (current clip when omitted)
- `--create/--no-create` (optional, default: `true`) — Create the remote version if missing on the selected source
- `--load/--no-load` (optional, default: `true`) — Load the remote version on every same-source timeline instance
- `--include-singletons` (optional, default: `false`) — Allow a one-off source to use remote scope

## Boundaries and gotchas

- Grouping and verification cover only the current timeline's video items.
- Name matching is exact and case-sensitive in the returned Remote Version list.
- `--no-create` produces a targeted validation error listing available remote versions when the name is absent.
- It does not restore prior local/remote version choices after verification.
- Do not infer activation from overall status in that mode.
- It does not save the project explicitly.
- It does not move the playhead itself.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color source-grade prepare-remote --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
