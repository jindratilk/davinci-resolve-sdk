# `project preset import`

Syntax: `cutagent project preset import PATH --name VALUE`

## Search terms

- import project settings preset
- project preset artifact
- explicit new preset name
- exact catalog insertion

## What it does

Import a project settings preset.

## Do not use when

Do not import over an existing preset name.

## Preflight and readback

Before execution, inspect the source provenance, run `project preset list`, and choose a new exact case-sensitive name.
After execution, require `imported:true`, retain `sourceSha256`, and confirm the exact name with `project preset list`. If the command reports uncertain state, inspect its state details before retrying; never assume a blind retry is safe.

## Public arguments and options

- `PATH` (required) — Project preset file path
- `--name` (required) — Exact new preset name

## Boundaries and gotchas

- Exact syntax is `cutagent project preset import PATH --name NAME`.
- NAME is exact and case-sensitive, must be nonempty, contain no NUL byte, and is limited to 1024 characters.
- Any catalog reorder, unexpected insertion, duplicate target, settings change, false acknowledgement, or unavailable readback fails closed.

## Examples

- `cutagent project preset import --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
