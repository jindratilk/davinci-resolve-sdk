# `fusion template assets add`

Syntax: `cutagent fusion template assets add TEMPLATE FILE [--overwrite]`

## Search terms

- add Fusion template asset
- copy asset beside template
- template assets folder
- install template dependency
- add PNG to Fusion template
- template asset overwrite
- asset copy dry-run
- Fusion external media asset

## What it does

Add an asset beside a Fusion template.

## Do not use when

Do not assume the template path is validated or exists. The command can create an asset tree for a nonexistent template.
Do not use source paths that contain the destination or vice versa. Recursive self-copy and source-equals-destination are not rejected.
Do not overwrite an existing asset without backing it up.
Do not expect the command to rewrite template references, validate asset type, refresh DaVinci Resolve, package the asset, or prove that the template uses it.

## Preflight and readback

Run `fusion template assets list` to confirm direct discovery.
For cleanup, restore/remove only the copied target and remove empty asset directories. Preserve/remove the source and template artifacts according to their own workflows.

## Public arguments and options

- `TEMPLATE` (required) — Template path
- `FILE` (required) — Asset path
- `--overwrite` (optional, default: `false`) — Replace an existing asset

## Boundaries and gotchas

- `--overwrite` is optional.
- It does not edit Fusion source to point at the copied asset.
- It does not refresh or inspect DaVinci Resolve.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fusion template assets add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
