# `fuse list`

Syntax: `cutagent fuse list`

## Search terms

- list installed Fusion Fuses
- find installed .fuse files
- recursive Fuse inventory
- DaVinci Resolve Fuse paths
- Fuse relative path
- custom Fusion tools inventory
- verify Fuse installation
- list nested Fuse files

## What it does

List installed Fuse files.

## Do not use when

Do not treat a listed path as proof that the Fuse is syntactically valid, safe, loaded, registered, compatible, or functional in DaVinci Resolve.
Do not use the `name` field alone as a unique identifier.
Do not expect global dry-run to provide a hypothetical future inventory.
The response contains no content-derived evidence.

## Preflight and readback

Before execution, determine whether the task concerns user-installed Fuses or vendor SDK examples. Record the expected Fuse root and whether nested installation directories are intentional.
Run the command in JSON mode. Treat an empty array as a valid state, not an error.
After installation or removal, run `fuse list` again and compare exact relative paths. Also confirm the destination directly because listing deliberately ignores wrong-suffix files and directories.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- The command does not open or validate file contents.
- `name` is only the basename and may be duplicated across nested directories.

## Examples

- `cutagent fuse list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
