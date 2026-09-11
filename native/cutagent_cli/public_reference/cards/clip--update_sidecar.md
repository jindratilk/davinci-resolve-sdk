# `clip update-sidecar`

Syntax: `cutagent clip update-sidecar [CLIP]`

## Search terms

- clip update-sidecar
- Update sidecar files for a timeline item.
- clip update-sidecar help
- clip update-sidecar command

## What it does

Update sidecar files for a timeline item.

## Do not use when

Avoid it on original production camera media until file ownership, backups, and the manufacturer's sidecar behavior are understood.

## Preflight and readback

Resolve the source file and confirm its format actually supports DaVinci Resolve sidecars. Prefer `--dry-run` first; this command's dry-run exits before connecting. A CLI boolean alone does not prove which bytes or settings changed.

## Public arguments and options

- `CLIP` (optional) — Clip name (current clip when omitted)

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent clip update-sidecar --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
