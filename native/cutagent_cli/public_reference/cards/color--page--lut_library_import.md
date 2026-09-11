# `color page lut-library-import`

Syntax: `cutagent color page lut-library-import SOURCE [--folder VALUE] [--overwrite] [--apply] [--clip VALUE] [--node VALUE] [--apply-lut VALUE]`

## Search terms

- import LUT library
- install cube LUT
- add LUTs to DaVinci Resolve
- refresh LUT list
- copy LUT folder
- bulk install cube files
- install and apply LUT
- add custom LUT pack
- register LUT in Color page

## What it does

Import LUTs into DaVinci Resolve LUT library and refresh the LUT list.

## Do not use when

Use `color lut --set` or `dctl-apply` when an already installed transform should only be attached to a node, and OS/file-management removal plus LUT refresh when uninstalling a library item. Use `cst-set` for editable color-space/gamma transforms.

## Preflight and readback

Before running, enumerate the source tree, review relative paths/names, determine the selected install root/folder and check for conflicts. When applying, verify the exact clip/node and chosen imported key. Retain source/hashes and manually remove test imports when finished.

## Public arguments and options

- `SOURCE` (required) — Local .cube file or directory of .cube LUTs to import
- `--folder` (optional, default: `"CutAgent/Imported"`) — Relative DaVinci Resolve LUT library folder
- `--overwrite` (optional, default: `false`) — Overwrite existing imported LUT files
- `--apply` (optional, default: `false`) — Apply the first imported LUT to a Color page node after refresh
- `--clip` (optional) — Clip name to apply the imported LUT to; defaults to current clip when --apply is used
- `--node` (optional, default: `1`) — Color node index for --apply
- `--apply-lut` (optional) — Specific imported LUT key to apply

## Boundaries and gotchas

- Closing or resetting the project does not remove copied LUTs.
- Identical existing files are reported unchanged without requiring `--overwrite`; same-path different hashes make the entire planning stage fail before any copy.
- No rendered-frame proof is performed after apply—only LUT-slot readback.

## Examples

- `cutagent color page lut-library-import --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
