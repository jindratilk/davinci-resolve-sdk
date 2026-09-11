# `ofx sample copy`

Syntax: `cutagent ofx sample copy NAME DEST [--overwrite]`

## Search terms

- copy OpenFX SDK sample
- copy GainPlugin.cpp
- OpenFX sample file copy
- copy OFX Makefile
- OpenFX developer source
- OFX sample dry-run
- copy SDK file by relative path
- overwrite copied OFX sample

## What it does

Copy an OpenFX example.

## Do not use when

Do not expect this command to copy a complete OpenFX sample project. The inventory contains files only, and each invocation copies exactly one file; headers, kernels, Makefiles, project files, and support libraries must be selected separately.
The command silently chooses the first sorted match.
Do not pass an untrusted or broad destination.
Do not use `--overwrite` without preserving the destination.
Do not assume the copied source is sufficient, compatible, licensed for the intended distribution, buildable, or safe. Review the SDK materials and all dependencies.
Do not expect copying to build, package, install, load, or test an OpenFX plugin in DaVinci Resolve.

## Preflight and readback

Before execution, verify the developer OpenFX root exists and independently enumerate files. Use the exact root-relative path, not an ambiguous basename.
Run global dry-run and confirm the exact source and destination selected, especially for names shared across projects.
Assemble and build a complete reviewed sample project separately. Validate/package/install the resulting bundle and prove DaVinci Resolve discovery/render behavior in a controlled environment.

## Public arguments and options

- `NAME` (required) — Sample name or relative path
- `DEST` (required) — Destination path
- `--overwrite` (optional, default: `false`) — Replace an existing destination

## Boundaries and gotchas

- `--overwrite` is the only command-specific option.
- The developer OpenFX root is fixed and cannot be overridden.
- Directories cannot be selected or copied by this command.
- Matching is exact and case-sensitive.
- All matches are collected, but only `matches[0]` is copied.
- Destination parents are created when the exact target path's parent does not exist.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent ofx sample copy --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
