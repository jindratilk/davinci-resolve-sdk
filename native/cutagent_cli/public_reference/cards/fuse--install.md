# `fuse install`

Syntax: `cutagent fuse install PATH [--overwrite]`

## Search terms

- install Fusion Fuse
- copy .fuse to user support folder
- DaVinci Resolve Fuse installation
- overwrite installed Fuse
- install custom Fusion tool
- install Fuse dry-run
- validate then install Fuse

## What it does

Install a Fuse file into the user DaVinci Resolve support folder.

## Do not use when

Do not install untrusted Fuse/Lua code.
Use `fuse validate` and independent source review before installation, but remember that the current validator is only a shallow suffix-and-substring test.
Do not use `--overwrite` when the installed destination must be preserved.
Do not expect installation to make a Fuse immediately available in an already-running DaVinci Resolve process. Discovery may require an application refresh or restart outside this command.

## Preflight and readback

Independently inspect any existing destination and preserve it before allowing overwrite.

## Public arguments and options

- `PATH` (required) — .fuse path
- `--overwrite` (optional, default: `false`) — Replace an existing installed Fuse

## Boundaries and gotchas

- `--overwrite` is the only command-specific option.
- Only the source basename determines the destination name.
- The command does not refresh, restart, or otherwise control DaVinci Resolve.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fuse install --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
