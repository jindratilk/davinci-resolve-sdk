# `workflow ui scaffold`

Syntax: `cutagent workflow ui scaffold [--python] [--lua] --name VALUE [--output VALUE] [--overwrite]`

## Search terms

- workflow UI scaffold
- Python UI script
- Lua UI script
- custom edit panel starter
- workflow integration panel

## What it does

Create a custom edit panel.

## Preflight and readback

Afterward, implement the SDK UI/event lifecycle, validate syntax, install appropriately, and test inside DaVinci Resolve.

## Public arguments and options

- `--python` (optional, default: `false`) — Create a Python script
- `--lua` (optional, default: `false`) — Create a Lua script
- `--name` (required) — UI script name
- `--output` (optional) — Output folder
- `--overwrite` (optional, default: `false`) — Replace existing generated scaffold files

## Boundaries and gotchas

- Exact syntax is `cutagent workflow ui scaffold [--python|--lua] --name NAME [--output DIR] [--overwrite]`.
- `--python` and `--lua` together are rejected.

## Examples

- `cutagent workflow ui scaffold --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
