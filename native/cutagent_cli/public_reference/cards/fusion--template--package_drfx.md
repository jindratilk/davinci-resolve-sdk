# `fusion template package-drfx`

Syntax: `cutagent fusion template package-drfx PATH --output VALUE [--overwrite]`

## Search terms

- package Fusion template
- create DRFX
- zip template folder
- Fusion .drfx bundle
- package template assets
- DRFX archive contents
- package template dry-run
- overwrite DRFX
- template bundle CRC
- DaVinci Resolve template package

## What it does

Package a Fusion template folder.

## Do not use when

It creates a generic ZIP-compatible archive.
Do not use `--overwrite` on an unverified path.
It does not walk the source tree.
Do not use it to install or test the package in DaVinci Resolve. Unpack/inspect separately and use an explicit installation workflow.

## Preflight and readback

Confirm source and output are not the same resolved path.
No DaVinci Resolve project state is changed by packaging itself.

## Public arguments and options

- `PATH` (required) — Template folder path
- `--output` (required) — Output .drfx path
- `--overwrite` (optional, default: `false`) — Replace an existing archive

## Boundaries and gotchas

- `--overwrite` is optional.
- File-source archives contain only the source basename.
- The command does not reject hidden files or inspect secrets.
- It does not generate or validate a DRFX manifest.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fusion template package-drfx --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
