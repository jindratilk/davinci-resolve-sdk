# `fusion template unpack-drfx`

Syntax: `cutagent fusion template unpack-drfx FILE --output VALUE [--overwrite]`

## Search terms

- unpack Fusion DRFX
- extract .drfx bundle
- inspect template archive
- Fusion template unzip
- DRFX members
- overwrite extracted template
- zip slip protection
- template archive conflict
- unpack dry-run
- verify DRFX contents

## What it does

Unpack a Fusion template package.

## Do not use when

Do not extract an untrusted archive merely because path traversal is blocked. There are no member-count, uncompressed-size, compression-ratio, duplicate-name, or disk-space limits.
Replacements are direct and unbacked.
Do not expect overwrite to clean the destination. Unrelated files and directories remain.
Do not expect unpacking to install, register, refresh, or test the template in DaVinci Resolve.

## Preflight and readback

Reject unexpected absolute, parent, hidden, duplicate, or oversized content.
No DaVinci Resolve project cleanup is required.

## Public arguments and options

- `FILE` (required) — .drfx bundle path
- `--output` (required) — Output directory
- `--overwrite` (optional, default: `false`) — Replace existing files

## Boundaries and gotchas

- `--overwrite` is optional.
- It does not pre-delete the destination or conflicting files.
- Duplicate archive member names are not rejected.
- The command does not validate DRFX layout, manifest, template kind, setting syntax, or assets.
- It does not return extracted hashes, byte counts, CRCs, or final inventory.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fusion template unpack-drfx --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
