# `dctl list`

Syntax: `cutagent dctl list`

## Search terms

- list DCTL files
- find installed DCTL
- show available DaVinci CTL transforms
- discover SDK DCTL examples
- locate .dctl paths
- inventory user DCTLs
- find DCTL relative name
- show DaVinci Resolve DCTL samples
- check DCTL installation
- browse custom color transforms

## What it does

List DCTL files in user and folders.

## Do not use when

Use `dctl install` to copy a transform, and inspect its returned destination directly for ACES installs.
Do not use this as a complete search of all DaVinci Resolve DCTL locations. In particular it omits the user ACES IDT/ODT directories and the system LUT library. Search the known destination explicitly when diagnosing an absolute-file `dctl apply` or an ACES install.

## Preflight and readback

Before listing, decide whether the question is “which files exist in these two roots,” “which transforms DaVinci Resolve currently recognizes,” or “which transform is applied.” Only the first is answered here. Preserve the full `path`/`root`, because identical basenames can occur in multiple rows.
After finding a candidate, run `dctl validate` on its full path and inspect its role (node transform, transition, IDT, ODT or plugin). Install/refresh if needed, then test it on an isolated Color version and confirm node readback plus rendered output.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- `dctl apply` may copy an absolute source into the system LUT root under `CutAgent/`; that copy is also invisible because only the user LUT root is scanned.
- Duplicate basenames are not collapsed.
- An empty array does not distinguish “nothing installed” from absent expected directories.
- Dry-run does not preview a future operation.

## Examples

- `cutagent dctl list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
