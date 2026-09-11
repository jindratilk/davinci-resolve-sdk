# `ofx validate`

Syntax: `cutagent ofx validate PATH_OR_BUNDLE`

## Search terms

- validate OpenFX bundle
- check .ofx.bundle path
- verify OFX path exists
- validate .bundle suffix
- OpenFX preflight
- check OFX file
- uppercase BUNDLE validation
- missing OFX bundle
- shallow OpenFX validation

## What it does

Check an OpenFX effect.

## Do not use when

Do not treat `valid:true` as proof of a valid OpenFX plugin. The command does not inspect bundle layout, Info.plist, executable files, OpenFX entry points, identifiers, architectures, dependencies, permissions, signatures, notarization, or code.
Do not use it as a security or provenance check.
Do not use it as proof of DaVinci Resolve discovery, compatibility, loadability, parameter behavior, image processing, or render output.
Do not assume the reported suffix preserves the full compound extension.

## Preflight and readback

Treat `valid` only as the two-predicate result.
Use controlled installation and restart/refresh of DaVinci Resolve for actual discovery.
The command is non-mutating.

## Public arguments and options

- `PATH_OR_BUNDLE` (required) — OpenFX project/bundle path

## Boundaries and gotchas

- It does not validate Info.plist or an OpenFX executable.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent ofx validate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
