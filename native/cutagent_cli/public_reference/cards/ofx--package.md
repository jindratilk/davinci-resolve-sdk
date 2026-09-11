# `ofx package`

Syntax: `cutagent ofx package PATH --output VALUE [--overwrite]`

## Search terms

- package OpenFX project
- create OFX ZIP archive
- package .ofx.bundle
- archive OpenFX source
- OpenFX package dry-run
- overwrite OFX package
- ZIP OpenFX bundle
- package hidden OFX files
- OpenFX distribution archive

## What it does

Package an OpenFX effect.

## Do not use when

All recursively discovered regular files, including dotfiles, are eligible.
Do not use `ofx validate` to prove package correctness.
The command provides no reproducibility controls.
Do not treat `packaged:true` as proof of archive integrity, plugin completeness, code signature, installation, DaVinci Resolve discovery, or render behavior.

## Preflight and readback

Record source file hashes.
Run global dry-run and confirm source/output inequality, exact output path, and overwrite state.
Install and test the extracted bundle separately in a controlled DaVinci Resolve environment.

## Public arguments and options

- `PATH` (required) — Project/bundle path
- `--output` (required) — Output bundle/zip path
- `--overwrite` (optional, default: `false`) — Replace an existing package file

## Boundaries and gotchas

- `--overwrite` is optional.
- File-source entry name is only the source basename.
- Packaging does not create a manifest, preserve empty directories, sign, notarize, compile, validate, install, or load a plugin.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent ofx package --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
