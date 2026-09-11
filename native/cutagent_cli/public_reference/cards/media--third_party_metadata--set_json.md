# `media third-party-metadata set-json`

Syntax: `cutagent media third-party-metadata set-json CLIP JSON_PAYLOAD`

## Search terms

- set multiple third-party metadata keys
- import namespaced metadata object
- set plugin metadata from JSON file
- merge custom Media Pool values
- attach JSON key values to clip

## What it does

Update third-party metadata.

## Do not use when

Use ordinary `media metadata` for standard DaVinci Resolve metadata.

## Public arguments and options

- `CLIP` (required) — Media Pool clip name
- `JSON_PAYLOAD` (required) — JSON object or path to JSON file

## Boundaries and gotchas

- JSON parsing occurs before dry-run.

## Examples

- `cutagent media third-party-metadata set-json --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
