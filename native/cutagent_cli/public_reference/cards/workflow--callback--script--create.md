# `workflow callback script create`

Syntax: `cutagent workflow callback script create KIND --output VALUE [--overwrite]`

## Search terms

- workflow callback script
- render start callback
- render stop callback
- resolve quit callback
- CommonJS event stub

## What it does

Prepare a custom edit connection.

## Do not use when

Do not use this to register, install, or execute the callback, or to generate arbitrary event handlers.

## Preflight and readback

Before execution, choose an exact supported kind and explicit output file, and preserve existing work unless `--overwrite` is intentional. Afterward, run `workflow node check`, implement real logic, and install/register it according to the Workflow Integration SDK.

## Public arguments and options

- `KIND` (required) — render-start|render-stop|resolve-quit
- `--output` (required) — Output script path
- `--overwrite` (optional, default: `false`) — Replace an existing script

## Boundaries and gotchas

- Exact syntax is `cutagent workflow callback script create KIND --output PATH [--overwrite]`.
- Kind matching is exact and case-sensitive.

## Examples

- `cutagent workflow callback script create --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
