# `lut list`

Syntax: `cutagent lut list [--resolve]`

## Search terms

- list installed LUTs
- user LUT inventory
- system DaVinci Resolve LUTs
- SDK LUT roots
- list cube files
- list DCTL files
- LUT relative path
- resolve LUT roots
- dry-run LUT listing

## What it does

List LUT files.

## Do not use when

Do not use this as proof that DaVinci Resolve has refreshed or discovered a listed file.
Do not use it to validate LUT syntax/content. Any matching file suffix is listed.
Do not assume `--resolve` means “query the running DaVinci Resolve application”; it only adds two local roots.
Do not expose raw output where local usernames, folder structure, or proprietary LUT names are sensitive; rows contain absolute paths.
Do not assume an empty result means DaVinci Resolve has no built-in LUTs.

## Preflight and readback

Before execution, decide whether user-only or expanded roots are required and whether absolute path disclosure is acceptable.
After removal, require that exact root/path tuple to disappear.
For application readiness, run `lut-refresh` with an active project and confirm the LUT is selectable/applied in DaVinci Resolve.

## Public arguments and options

- `--resolve` (optional, default: `false`) — Include system/DaVinci Resolve SDK LUT roots

## Boundaries and gotchas

- The only command option is `--resolve`.
- `--resolve` adds `/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT`.
- `--resolve` also adds `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/LUT`.

## Examples

- `cutagent lut list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
