# `codec validate`

Syntax: `cutagent codec validate BUNDLE`

## Search terms

- validate codec plugin bundle
- check IOPlugin path
- confirm codec file exists
- verify plugin extension
- preflight codec installation
- test bundle suffix

## What it does

Check a codec add-on.

## Do not use when

Use binary inspection, code-signature verification, SDK-specific validation, and a real render through DaVinci Resolve when “valid” means loadable and functional.

## Preflight and readback

After install, validate the returned destination path and compare source/destination content. Finally restart DaVinci Resolve if needed and prove the codec is exposed and can encode; only that closes the gap left by this shallow preflight.

## Public arguments and options

- `BUNDLE` (required) — Plugin bundle/path

## Boundaries and gotchas

- It does not distinguish source paths from installed paths, user paths from system paths, or macOS bundles from Windows/Linux binaries.
- Suffix comparison is case-insensitive, whereas `codec list-installed` uses lowercase glob patterns that may be case-sensitive on some filesystems.

## Examples

- `cutagent codec validate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
