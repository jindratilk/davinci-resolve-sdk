# `ofx scaffold`

Syntax: `cutagent ofx scaffold KIND NAME [--output VALUE] [--overwrite]`

## Search terms

- scaffold OpenFX plugin
- create OpenFX filter project
- create OpenFX transition project
- generate OFX C++ starter
- OpenFX SDK scaffold
- scaffold plugin README
- OpenFX scaffold dry-run
- overwrite OFX scaffold
- minimal OpenFX source

## What it does

Prepare an OpenFX effect project.

## Do not use when

Do not treat the output as a compilable or loadable OpenFX plugin.
The name is also interpolated into file contents without escaping.
Do not use an arbitrary kind or different capitalization. `filter` and `transition` are the only exact accepted strings.
Do not overwrite an existing scaffold without preserving it.
Do not expect this command to compile, package, install, register, load, or test an OpenFX plugin in DaVinci Resolve.

## Preflight and readback

Choose an explicit isolated output folder.
Resolve each independently and prove it remains below the intended output root.
Build and validate the completed bundle separately, then use a controlled DaVinci Resolve environment for discovery and render verification.

## Public arguments and options

- `KIND` (required) — filter|transition
- `NAME` (required) — Plugin name
- `--output` (optional) — Output folder
- `--overwrite` (optional, default: `false`) — Replace existing generated scaffold files

## Boundaries and gotchas

- `--output TEXT` and `--overwrite` are optional.
- The README contains only a heading, blank line, and one generated-kind sentence.
- Dry-run with overwrite listed both conflicts and preserved the original hashes.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent ofx scaffold --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
