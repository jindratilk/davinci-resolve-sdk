# `fuse uninstall`

Syntax: `cutagent fuse uninstall NAME`

## Search terms

- uninstall Fusion Fuse
- remove installed .fuse
- delete user Fuse
- uninstall Fuse by name
- Fuse cleanup
- Fuse uninstall dry-run
- remove custom Fusion tool
- missing Fuse uninstall

## What it does

Uninstall a Fuse file.

## Do not use when

Do not use this command without first resolving the exact installed path.
Do not use it to remove installed Fuse directories.
Do not pass an absolute path.
Do not interpret `removed:false` as an execution failure.
Do not expect the command to remove references, nodes, cached code, rendered media, settings, or effects already present in a DaVinci Resolve project.

## Preflight and readback

Independently verify that the target still exists afterward.
For `removed:true`, prove the exact path is absent and run `fuse list` again.
If DaVinci Resolve was running, verify application state separately.
Never delete or overwrite unrelated user Fuses.

## Public arguments and options

- `NAME` (required) — Fuse name or file name

## Boundaries and gotchas

- Suffix testing is case-sensitive.
- There is a cross-command mismatch: `fuse install` supports directories, while `fuse uninstall` cannot remove them.
- It does not modify open compositions or remove existing Fuse nodes from a project.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fuse uninstall --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
