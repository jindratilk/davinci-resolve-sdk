# `media third-party-metadata get`

Syntax: `cutagent media third-party-metadata get CLIP [KEY]`

## Search terms

- get vendor metadata key
- inspect custom namespaced clip data
- list external metadata fields
- query custom Media Pool item value
- get third-party metadata dictionary
- check missing custom metadata key

## What it does

Read third-party metadata from a media pool item.

## Do not use when

Use `media metadata` for standard DaVinci Resolve fields such as Comments, Keywords, Scene, or Sound Roll. Use `media info` for technical clip properties.

## Preflight and readback

Treat key names as exact/case-sensitive opaque strings. After any set/set-json operation, use both keyed and full getters to verify the changed value and ensure unrelated keys remain.

## Public arguments and options

- `CLIP` (required) — Media Pool clip name
- `KEY` (optional) — Optional metadata key

## Boundaries and gotchas

- Since custom metadata is per Media Pool object, choosing a same-source duplicate in another bin can return a different dictionary.
- Agents must not overwrite unknown keys merely because they appear readable.

## Examples

- `cutagent media third-party-metadata get --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
