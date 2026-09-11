# `asset resolve`

Syntax: `cutagent asset resolve [--candidates VALUE] [--candidates-file VALUE] [--require] [--mode VALUE]`

## Search terms

- find first available asset
- resolve Fusion template path
- find Media Pool clip by name
- disambiguate template or media
- validate asset candidates
- resolve all available assets

## What it does

Locate an asset file.

## Do not use when

Do not use it to list recent generated proof files by modification time; use `asset artifact-index`.

## Preflight and readback

Prepare candidates in intentional preference order, with an explicit kind where type confusion matters. For templates validate content; for Media Pool matches run the domain's identity/info readback; after the later mutation verify that mutation separately because asset resolution itself changes nothing.

## Public arguments and options

- `--candidates` (optional) — Inline candidates JSON, or a path to a JSON file
- `--candidates-file` (optional) — Path to candidates JSON
- `--require` (optional, default: `false`) — Fail with ASSET_NOT_FOUND when no candidate resolves
- `--mode` (optional, default: `"first"`) — Resolution mode: first|all

## Boundaries and gotchas

- Exactly one of `--candidates` and `--candidates-file` is required.
- Candidate indices are zero-based array positions, unlike many DaVinci Resolve CLI track/timeline indices.
- Ambiguous Media Pool/template matches are not selected even though files were found.
- File candidates only check that a regular file exists; `kind` is carried through but the extension/content is not validated against it.

## Examples

- `cutagent asset resolve --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
