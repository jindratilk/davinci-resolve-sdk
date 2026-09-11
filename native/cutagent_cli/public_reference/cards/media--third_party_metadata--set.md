# `media third-party-metadata set`

Syntax: `cutagent media third-party-metadata set CLIP KEY VALUE`

## Search terms

- set third-party Media Pool metadata
- add vendor metadata key
- store plugin data on source clip
- attach custom key value to media
- set integration metadata

## What it does

Set one third-party metadata key on a media pool item.

## Do not use when

Use `media metadata CLIP KEY VALUE` for standard DaVinci Resolve metadata such as Comments/Keywords. Do not repurpose keys owned by another plugin/vendor; choose a namespaced key and preserve unknown entries.

## Public arguments and options

- `CLIP` (required) — Media Pool clip name
- `KEY` (required) — Metadata key
- `VALUE` (required) — Metadata value

## Boundaries and gotchas

- Setting an existing key via set-json later replaced only that key and retained the rest.

## Examples

- `cutagent media third-party-metadata set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
