# `project cloud open`

Syntax: `cutagent project cloud open NAME [--media-path VALUE] [--sync-mode VALUE]`

## Search terms

- open Blackmagic Cloud project
- cloud project media path
- Blackmagic Cloud login UI
- activate cloud project
- DaVinci Resolve Cloud library

## What it does

Open a cloud project.

## Do not use when

Do not rely on it unattended unless DaVinci Resolve is already authenticated to the intended Blackmagic Cloud account/library.

## Preflight and readback

Record any login or conflict UI and ensure opening the project did not unexpectedly switch sync/storage behavior.

## Public arguments and options

- `NAME` (required) — Cloud project name
- `--media-path` (optional) — Cloud media path
- `--sync-mode` (optional) — Cloud sync mode

## Boundaries and gotchas

- Dry-run does not echo media path or sync mode.
- There is no confirmation or `--force` option even though opening changes current project context.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent project cloud open --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
