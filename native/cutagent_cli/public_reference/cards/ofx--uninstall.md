# `ofx uninstall`

Syntax: `cutagent ofx uninstall PLUGIN_ID`

## Search terms

- uninstall OpenFX plugin
- remove user OFX bundle
- delete .ofx.bundle
- uninstall OFX by plugin id
- OpenFX cleanup
- OFX uninstall dry-run
- remove custom OFX plugin
- missing OFX uninstall

## What it does

Uninstall a user OpenFX bundle.

## Do not use when

Do not run the command without first enumerating and independently resolving the exact target.
Do not use a short id when multiple candidate forms exist.
Do not pass an absolute path or any path that resolves outside the OFX root. Containment checks reject both.
Do not expect removal to unload a plugin from a running DaVinci Resolve process, remove nodes from projects, delete caches, or repair compositions that reference it.
Do not interpret `removed:false` as a CutAgent CLI error.

## Preflight and readback

Resolve all three candidate names explicitly.
Independently verify that the complete bundle remains after dry-run.
Remove newly created empty OFX parents only when pre-state evidence proves they did not exist.

## Public arguments and options

- `PLUGIN_ID` (required) — Plugin ID/folder name

## Boundaries and gotchas

- Dry-run on a missing target also returns not-found rather than a removal plan.
- The command does not refresh, restart, or contact DaVinci Resolve.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent ofx uninstall --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
