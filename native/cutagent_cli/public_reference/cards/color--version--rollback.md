# `color version rollback`

Syntax: `cutagent color version rollback NAME [--remote] [--clip VALUE]`

## Search terms

- roll back color grade
- restore earlier grade version
- revert clip look to named version
- return to known good color version
- undo grading experiment with version
- recover previous Color page take
- switch back to saved grade
- restore local color checkpoint
- abandon current grade branch
- recall earlier clip correction
- revert active grading version

## What it does

Roll back to a color version.

## Do not use when

Use `color reset` when the goal is an ungraded/default clip rather than a saved named version.
Do not target a duplicated version name because name/type verification cannot identify which occurrence loaded.

## Preflight and readback

Confirm the named target was actually validated as good; the command cannot infer chronology or quality from names.
Confirm version inventories did not change, inspect the restored nodes/parameters, and render/export a representative frame to prove visual restoration. If this was a temporary comparison, switch back explicitly; otherwise save the project after validating the chosen grade.

## Public arguments and options

- `NAME` (required) — Version name to roll back to
- `--remote` (optional, default: `false`)
- `--clip` (optional)

## Boundaries and gotchas

- The target is selected solely by exact normalized name plus type; the command has no timestamp, previous-version stack or `--steps` option.
- Duplicate names are ambiguous.
- Verification can prove only that the current name/type matches, not which same-name row DaVinci Resolve selected.
- `--remote` is mandatory for a remote checkpoint even when the same name is absent locally.
- Without it, only local type 0 is requested.
- There is no `--force` requirement even though active grade state changes.
- The command does not save the project.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent color version rollback --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
