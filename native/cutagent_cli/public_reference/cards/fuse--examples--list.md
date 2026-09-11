# `fuse examples list`

Syntax: `cutagent fuse examples list`

## Search terms

- list Fuse SDK examples
- DaVinci Resolve developer Fuses
- Fusion Fuse sample inventory
- find Arrow.fuse
- list vendor Fuse examples
- Fusion SDK example paths
- Fuse developer samples
- inspect installed Fuse examples

## What it does

List Fuse examples.

## Do not use when

Do not use this command to list user-installed Fuses.
Do not rely on the inventory when the optional DaVinci Resolve developer materials are not installed. An empty array does not distinguish a missing root from an empty root.
Do not use `name` as a unique identity if the SDK ever includes nested examples with duplicate basenames; use the full or relative path.
Do not expect global dry-run to simulate a different SDK installation.
Do not use this output as source integrity evidence.

## Preflight and readback

Before execution, verify that the task concerns vendor SDK examples rather than user-installed Fuses and record the expected developer root for the target platform.
Run the command in JSON mode and branch on the returned array.
After selecting an example, use its exact `path`; quote names containing spaces.
Use `fuse examples install` with dry-run before copying an example into the user Fuse root. After installation, compare source and destination hashes and verify it through `fuse list`.
Remove only the installed copy afterward; never modify the vendor source.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- The command does not search arbitrary SDK locations or accept a root override.
- The listing itself has no side effects and required no cleanup.
- No example was loaded into a composition during this read-only command verification.

## Examples

- `cutagent fuse examples list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
