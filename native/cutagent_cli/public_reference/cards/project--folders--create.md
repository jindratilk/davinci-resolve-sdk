# `project folders create`

Syntax: `cutagent project folders create NAME`

## Search terms

- organize DaVinci Resolve projects
- project library subfolder
- folder existence readback
- idempotent folder create
- project manager folder

## What it does

Create a new folder.

## Do not use when

Do not use blank/whitespace or path-like names. The command performs no local name validation or trimming.

## Preflight and readback

Because matching is exact, verify casing and whitespace.
Open it and return to the prior folder to verify navigation.

## Public arguments and options

- `NAME` (required) — Folder name

## Boundaries and gotchas

- There is no `--force` or confirmation.
- The command connects before dry-run.
- Existence matching is exact/case-sensitive after converting entries to strings.
- Verification does not confirm current path or uniqueness beyond exact list membership.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent project folders create --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
