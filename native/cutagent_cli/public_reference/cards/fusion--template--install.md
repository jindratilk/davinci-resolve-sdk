# `fusion template install`

Syntax: `cutagent fusion template install PATH --kind VALUE [--overwrite]`

## Search terms

- install Fusion template
- copy template to DaVinci Resolve
- user Fusion Titles folder
- install .setting title
- install generator template
- install effect template
- install transition template
- Fusion template support folder
- overwrite installed template
- template install dry-run
- install template discovery

## What it does

Install a Fusion template into the user DaVinci Resolve templates folder.

## Do not use when

Do not install an unreviewed or shallowly validated template.
Do not rely on the help text to enforce kind.
Do not assume installation refreshes the DaVinci Resolve Effects Library or proves GUI visibility. The command never contacts DaVinci Resolve or triggers a refresh.
Do not use `fusion template list` to verify this installation; that command does not enumerate nested DaVinci Resolve template folders.

## Preflight and readback

Confirm the destination does not belong to an existing user template. Run global dry-run and require the correct mapped folder, basename, operation, and overwrite flags.
For cleanup, use the matching uninstall command with the same kind and unique name, verify the destination is absent, and confirm bare-name resolution fails again. Preserve or separately remove the source artifact according to its workflow.

## Public arguments and options

- `PATH` (required) — .setting path
- `--kind` (required) — title|generator|effect|transition
- `--overwrite` (optional, default: `false`) — Replace an existing installed template

## Boundaries and gotchas

- `--overwrite` is optional.
- Because arbitrary kind text becomes a path component, untrusted absolute/traversal-like values must not be accepted.
- Conflict validation runs before dry-run output.
- The command does not make an atomic swap.
- It does not register, refresh, index, or display the template in DaVinci Resolve.
- Cleanup uninstall removed only the unique target.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fusion template install --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
