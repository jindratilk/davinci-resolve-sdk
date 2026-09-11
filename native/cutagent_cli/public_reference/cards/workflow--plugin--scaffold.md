# `workflow plugin scaffold`

Syntax: `cutagent workflow plugin scaffold PLUGIN_ID --name VALUE [--output VALUE] [--overwrite]`

## Search terms

- scaffold workflow plugin
- create manifest.json
- minimal workflow integration
- workflow SDK starter

## What it does

Prepare a custom add-on.

## Preflight and readback

Before execution, choose a real plugin id/name and isolated destination. Afterward, implement behavior, compare against the installed DaVinci Resolve Workflow Integration SDK, validate, test, package, and install deliberately.

## Public arguments and options

- `PLUGIN_ID` (required) — Plugin ID
- `--name` (required) — Plugin display name
- `--output` (optional) — Output folder
- `--overwrite` (optional, default: `false`) — Replace existing generated scaffold files

## Boundaries and gotchas

- Only the two generated files are conflict-checked.

## Examples

- `cutagent workflow plugin scaffold --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
