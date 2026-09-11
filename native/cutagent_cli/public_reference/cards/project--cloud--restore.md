# `project cloud restore`

Syntax: `cutagent project cloud restore FOLDER [--name VALUE] [--media-path VALUE]`

## Search terms

- restore Blackmagic Cloud project
- cloud archive restore
- restored cloud project name
- cloud media path
- Blackmagic Cloud authentication

## What it does

Restore a cloud project folder.

## Preflight and readback

Dry-run checks only command shape.

## Public arguments and options

- `FOLDER` (required) — Cloud project backup folder
- `--name` (optional) — Restored project name
- `--media-path` (optional) — Cloud media path

## Boundaries and gotchas

- Dry-run returns before connecting, resolving constants, validating folder, or negotiating methods.
- Dry-run does not echo optional destination settings.
- There is no `--force` or confirmation gate.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent project cloud restore --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
