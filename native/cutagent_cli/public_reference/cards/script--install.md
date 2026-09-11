# `script install`

Syntax: `cutagent script install PATH [--page VALUE] [--name VALUE] [--all-users] [--overwrite]`

## Search terms

- install DaVinci Resolve script
- Fusion Scripts page folder
- Utility Edit Color Deliver Fusion script
- all-users script install
- overwrite installed script
- copy script into support folder
- DaVinci Resolve menu script
- script installation dry-run

## What it does

Install a DaVinci Resolve custom edit.

## Do not use when

Do not install untrusted executable code or a source tree that has not been reviewed.

## Preflight and readback

Before execution, inspect the source contents and type, choose one exact case-sensitive page, and run dry-run. Verify the reported destination remains under the intended user or system Scripts root and does not already contain user work.
Prefer omitting `--name` so the safe source basename is used. Back up an existing destination before an approved overwrite.
Remove it with the matching page/scope when no longer needed.

## Public arguments and options

- `PATH` (required) — Script path
- `--page` (optional, default: `"Utility"`) — Utility|Edit|Color|Deliver|Fusion
- `--name` (optional) — Installed file name
- `--all-users` (optional, default: `false`) — Install into the system support folder
- `--overwrite` (optional, default: `false`) — Replace an existing installed script

## Boundaries and gotchas

- Exact help is `cutagent script install PATH [--page PAGE] [--name NAME] [--all-users] [--overwrite]`.
- Page text is stripped but remains case-sensitive.
- Source must exist even in dry-run.
- User-scope root is the macOS path under `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/PAGE`.
- When `--name` is omitted or empty, the source basename is used.
- An absolute `--name` replaces the page-root path entirely under `pathlib` joining.
- This is a path-confinement hazard; always verify dry-run destination.
- Dry-run performs source, page, destination-type, and existing-conflict checks without copying.
- Existing destinations are rejected unless `--overwrite` is supplied.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent script install --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
