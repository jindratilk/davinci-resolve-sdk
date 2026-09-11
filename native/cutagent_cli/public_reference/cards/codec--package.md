# `codec package`

Syntax: `cutagent codec package PATH --arch VALUE [--overwrite]`

## Search terms

- zip codec plugin bundle
- package DaVinci Resolve IOPlugin
- create architecture-labelled codec archive
- prepare encoder plugin distribution
- bundle codec project for MacOS
- package codec for Win64

## What it does

Package a codec add-on.

## Do not use when

Do not use this as a general archive command when the required output location or archive root layout differs; the codec command fixes both. Use the repository’s release packaging workflow if it defines manifests, checksums, signatures, or multi-architecture assembly.

## Preflight and readback

Before packaging, inspect and test the bundle, remove unintended build/cache/secret files, confirm its binary architectures, and dry-run to record the exact sibling output path.

## Public arguments and options

- `PATH` (required) — Project/bundle path
- `--arch` (required) — MacOS|MacOS-x86-64|Linux-x86-64|Win64
- `--overwrite` (optional, default: `false`) — Replace an existing package file

## Boundaries and gotchas

- Existing output is rejected unless `--overwrite`; overwrite removes the previous archive before writing the new one.

## Examples

- `cutagent codec package --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
