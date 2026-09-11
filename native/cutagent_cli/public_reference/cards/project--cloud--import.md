# `project cloud import`

Syntax: `cutagent project cloud import FILE_PATH [--name VALUE] [--media-path VALUE]`

## Search terms

- import Blackmagic Cloud project
- cloud project file import
- upload DRP to cloud
- imported cloud project name
- cloud media path setting
- Blackmagic Cloud login

## What it does

Import a cloud project.

## Do not use when

Do not use this for a local project import; use `project import`.
The command performs no local file checks.
Do not treat success as proof that media uploaded or relinked. `--media-path` configures Cloud media location; it does not validate or transfer source media itself.

## Preflight and readback

Dry-run confirms only command shape, not file or account readiness.

## Public arguments and options

- `FILE_PATH` (required) — Cloud project file
- `--name` (optional) — Imported project name
- `--media-path` (optional) — Cloud media path

## Boundaries and gotchas

- Dry-run with name/media path returns only the file path, so it cannot audit effective settings.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent project cloud import --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
