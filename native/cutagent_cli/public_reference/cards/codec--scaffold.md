# `codec scaffold`

Syntax: `cutagent codec scaffold KIND NAME [--output VALUE] [--overwrite]`

## Search terms

- create codec encoder plugin starter
- scaffold DaVinci Resolve IOPlugin
- start codec SDK project
- generate encoder C++ skeleton
- make a codec plugin folder
- bootstrap custom render encoder

## What it does

Prepare a codec add-on project.

## Do not use when

Use `codec sample copy x264 DEST` when actual SDK headers, Makefiles, wrapper code, Visual Studio files, and a working plugin layout are needed. Use `codec build` only after the project has a Makefile, `codec package` for an existing project/bundle, and `codec install` for a finished bundle.

## Preflight and readback

Run a dry-run to record the two exact target paths. Verify those project-specific additions independently; successful scaffolding proves only that the two starter files were written.

## Public arguments and options

- `KIND` (required) — encoder
- `NAME` (required) — Plugin name
- `--output` (optional) — Output folder
- `--overwrite` (optional, default: `false`) — Replace existing generated scaffold files

## Boundaries and gotchas

- Only the exact kind `encoder` is accepted.
- `--overwrite` is file-scoped, not a clean regeneration.
- Without `--overwrite`, a conflict in either generated file rejects the whole scaffold before any file is written.

## DaVinci Resolve editions

Use `codec sample copy x264 DEST` when actual SDK headers, Makefiles, wrapper code, Visual Studio files, and a working plugin layout are needed.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent codec scaffold --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
