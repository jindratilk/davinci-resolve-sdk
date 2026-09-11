# `project cloud create`

Syntax: `cutagent project cloud create NAME [--media-path VALUE] [--sync-mode VALUE] [--collab]`

## Search terms

- create Blackmagic Cloud project
- cloud project media path
- cloud sync mode
- collaborative cloud project
- Blackmagic Cloud login
- DaVinci Resolve cloud settings

## What it does

Create a cloud project.

## Do not use when

It ignores those details in its response.
Do not assume arbitrary sync-mode strings are rejected.

## Preflight and readback

Test access from another authorized collaborator/device when collaboration was requested, and confirm no unintended login modal blocks automation.

## Public arguments and options

- `NAME` (required) — Cloud project name
- `--media-path` (optional) — Cloud media path
- `--sync-mode` (optional) — Cloud sync mode
- `--collab` (optional, default: `false`) — Enable collaboration when supported

## Boundaries and gotchas

- `proxy` maps to proxy-only; `original` maps to proxy-and-original.
- Collaboration is included only when true; false means the key is omitted.
- Consequently, dry-run with an unknown sync mode still succeeds.
- No `--force` or confirmation gate is exposed.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent project cloud create --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
