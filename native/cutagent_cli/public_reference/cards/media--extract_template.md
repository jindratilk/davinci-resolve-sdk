# `media extract-template`

Syntax: `cutagent media extract-template CLIP [--fields VALUE] [--exact] [--folder VALUE] [--allow-temp-append] [--temp-track VALUE] [--temp-duration VALUE] [--temp-gap VALUE] [--include-nested] [--cleanup] [--json]`

## Search terms

- extract Fusion title wording
- inspect template image path
- get logo source from template clip
- inspect nested compound title
- extract template text and image metadata
- find image used by Fusion template
- inspect title without placing it permanently

## What it does

Extract text and image metadata from a media pool template clip.

## Do not use when

Use `media info` or `media metadata` when ordinary Media Pool properties are the goal rather than template-specific text/image discovery. Use Fusion composition inspection commands for an existing timeline item's full node graph or arbitrary tool inputs; this command only searches a small fixed set of text/image keys and returns the first match. Use storage/file inspection when only the source file path is needed: requesting `image` on ordinary footage can simply return its general `File Path`.

## Preflight and readback

Search/list candidates and use `--exact` plus `--folder` whenever names can collide. Request only the field actually needed; first run without temp append and inspect the attempt trace. Validate extracted text/image against the actual template render rather than trusting a generic property with a matching key.

## Public arguments and options

- `CLIP` (required) — Media Pool clip name, id, or source path
- `--fields` (optional, default: `"text,image"`) — Comma-separated fields: text,image
- `--exact` (optional, default: `false`) — Require an exact name/id/path match
- `--folder` (optional) — Disambiguate by Media Pool folder path
- `--allow-temp-append/--no-temp-append` (optional, default: `false`) — Allow a reversible temporary timeline append
- `--temp-track` (optional) — Video track for the temporary append
- `--temp-duration` (optional, default: `"1s"`) — Temporary append duration
- `--temp-gap` (optional, default: `"1s"`) — Gap after current timeline end for temporary append
- `--include-nested/--no-include-nested` (optional, default: `true`) — Inspect nested/compound timeline contents when available
- `--cleanup/--keep-temp` (optional, default: `true`) — Delete the temporary item created by this command
- `--json/-j` (optional, default: `false`) — JSON output

## Boundaries and gotchas

- It also moved playhead from frame 86448 to 86466. “Cleanup” covers only the temporary clip.
- Supplying a higher `--temp-track` can itself leave new tracks.
- The insertion point is timeline end plus `--temp-gap`; durations/gaps use CutAgent time syntax converted at active timeline fps and must resolve above zero.
- `--keep-temp` deliberately leaves the occurrence.
- Do not repeat temp appends once the trace proves the field is not exposed.

## Stable public error codes

- `AMBIGUOUS_MEDIA_POOL_ITEM`

## Examples

- `cutagent media extract-template --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
