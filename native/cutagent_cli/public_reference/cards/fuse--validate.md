# `fuse validate`

Syntax: `cutagent fuse validate PATH`

## Search terms

- validate Fusion Fuse
- check .fuse source
- FuRegisterClass check
- Fuse SDK validation
- malformed Fuse false positive
- validate installed Fuse example
- Fuse suffix validation
- static Fuse preflight
- DaVinci Resolve Fuse source check

## What it does

Validate a Fuse file.

## Do not use when

Do not treat `valid:true` as proof that a Fuse compiles, loads, registers safely, exposes usable inputs/outputs, processes frames, or is compatible with the installed DaVinci Resolve version.
Do not use it as a security check.
Do not rely on it to reject malformed quoting or commented/dead registration text. Any case-sensitive substring occurrence is enough.
Do not use it as proof that DaVinci Resolve has discovered an installed Fuse.
Do not validate a very large untrusted file without an independent size limit.

## Preflight and readback

Never alter the vendor or user source being inspected.

## Public arguments and options

- `PATH` (required) — .fuse path

## Boundaries and gotchas

- The command does not compare registered name with filename.
- It does not modify the file or DaVinci Resolve state.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fuse validate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
