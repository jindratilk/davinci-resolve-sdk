# `codec install`

Syntax: `cutagent codec install BUNDLE [--overwrite]`

## Search terms

- install codec plugin
- add DaVinci Resolve IOPlugin
- install custom encoder bundle
- copy codec into user support folder
- enable third-party render codec
- deploy codec plugin locally

## What it does

Install a codec add-on.

## Do not use when

Use `codec validate` first for the command’s limited existence/suffix check, and the plugin vendor or operating-system installer when system-wide placement, privileged files, dependencies, signing, or registration is required.

## Preflight and readback

Before copying, inspect the source bundle recursively, verify its architecture/signature and exact basename, run `codec validate`, and run install with global dry-run to see the destination and overwrite status.

## Public arguments and options

- `BUNDLE` (required) — Plugin bundle/path
- `--overwrite` (optional, default: `false`) — Replace an existing installed bundle

## Boundaries and gotchas

- An already existing destination is rejected unless `--overwrite`.
- Installation does not notify or refresh the running DaVinci Resolve process.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent codec install --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
