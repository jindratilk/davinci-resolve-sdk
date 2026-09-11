# `fusion template uninstall`

Syntax: `cutagent fusion template uninstall NAME --kind VALUE`

## Search terms

- uninstall Fusion template
- remove installed .setting
- delete user Fusion title
- remove generator template
- remove effect template
- remove transition template
- template uninstall dry-run
- installed template cleanup
- remove DaVinci Resolve template
- template not found

## What it does

Remove an installed Fusion template.

## Do not use when

Do not expect the help text to enforce kind.
It unlinks one existing path only.
If an extensionless path of the same name exists, that literal target wins.

## Preflight and readback

Independently confirm the file remains afterward.
Confirm the restore source remains intact.
Refresh/restart DaVinci Resolve separately if its UI caches template inventory.

## Public arguments and options

- `NAME` (required) — Template name
- `--kind` (required) — title|generator|effect|transition

## Boundaries and gotchas

- Existing-target dry-run returns an operation plan and does not unlink.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fusion template uninstall --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
