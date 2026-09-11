# `project preset list`

Syntax: `cutagent project preset list`

## Search terms

- list project presets
- DaVinci Resolve project settings presets
- preset names
- project preset inventory
- preset index
- current project presets

## What it does

List project presets.

## Do not use when

Do not treat the displayed index as a stable preset ID.

## Preflight and readback

Before execution, open the intended project and ensure preset APIs are available.
After execution, use the exact displayed preset name for `project preset load`.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- There are no local options; `--all` is invalid.
- Preferred result must be a list; other shapes are ignored.
- Methods are called directly; exceptions are handled only by the outer command wrapper.
- Empty output does not reveal which methods were checked.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent project preset list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
