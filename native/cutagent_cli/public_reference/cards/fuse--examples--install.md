# `fuse examples install`

Syntax: `cutagent fuse examples install NAME [--overwrite]`

## Search terms

- install Fuse SDK example
- install Arrow.fuse
- copy vendor Fuse example
- DaVinci Resolve developer Fuse install
- install Fusion sample
- overwrite installed Fuse example
- Fuse example dry-run
- user Fuse folder from SDK
- test Fusion Fuse example

## What it does

Install a Fuse example.

## Do not use when

Do not use the command with an abbreviated, suffixless, or case-insensitive example name. Selection is an exact, case-sensitive basename comparison; obtain `name` from `fuse examples list`.
Do not treat vendor example status as a production safety or compatibility guarantee. The command does not inspect source, validate syntax, check DaVinci Resolve version compatibility, sandbox code, or load the Fuse.
Do not use `--overwrite` unless the existing user-installed destination may be discarded.
Do not expect the command to refresh or restart DaVinci Resolve.
Do not use this command when the developer materials are absent.
Do not modify the system vendor source as part of testing. Install a user copy, compare hashes, and remove only that copy.

## Preflight and readback

Run `fuse validate` on the vendor source only as a shallow preflight, then run global dry-run. Preserve any existing user destination independently before allowing overwrite.
Run `fuse list` and confirm the exact relative path; optionally run `fuse validate` on the installed copy.

## Public arguments and options

- `NAME` (required) — Fuse example file name
- `--overwrite` (optional, default: `false`) — Replace an existing installed Fuse

## Boundaries and gotchas

- `--overwrite` is the only command-specific option.
- Spaces and suffixes are part of the exact name and must be shell-quoted where applicable.
- The command does not accept an arbitrary source path; use `fuse install` for a reviewed custom source.
- `fuse validate` on the installed copy returned `valid:true`, which is only a shallow check.
- The command does not refresh, restart, load, compile, or execute the example.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fuse examples install --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
