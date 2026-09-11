# `codec uninstall`

Syntax: `cutagent codec uninstall NAME`

## Search terms

- uninstall codec plugin
- remove DaVinci Resolve IOPlugin
- delete custom encoder bundle
- remove user codec extension
- clean up installed codec
- disable local codec plugin

## What it does

Remove a codec add-on.

## Do not use when

Use `ofx uninstall`, `fuse uninstall`, workflow-plugin removal, or LUT removal for those different extension families. Do not use this to remove a system-wide codec installation or vendor-managed dependencies; it is constrained to the per-user DaVinci Resolve IOPlugins root. If multiple versions or suffix variants exist, inspect `codec list-installed` and pass the exact relative path for each, because one invocation removes only the first matching candidate.

## Preflight and readback

After deletion, run `codec list-installed` again and inspect the target path.

## Public arguments and options

- `NAME` (required) — Plugin name/folder

## Boundaries and gotchas

- A dylib must be supplied with its full filename.
- Removing files while DaVinci Resolve is open does not unload code already in memory.

## Examples

- `cutagent codec uninstall --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
