# `media proxy link-fullres`

Syntax: `cutagent media proxy link-fullres CLIP PATH [--dry-run] [--json]`

## Search terms

- link proxy clip to full resolution original
- attach camera original to proxy
- conform proxy to original media
- replace proxy identity with source master
- online a proxy-only Media Pool item
- link high resolution file
- proxy to camera negative

## What it does

Link full-resolution media for a clip.

## Do not use when

Use `media proxy CLIP --link PATH` when a full-resolution source item already exists and a lightweight proxy should be attached to it; that direction is the inverse of this command. Use `media replace` when replacing source content without preserving the old file as a proxy. Do not use this as an import command for an unrelated high-resolution file: it changes the source identity of the existing item and requires the files to represent the same shot.

## Preflight and readback

Record the item's Media Pool ID, folder, current `File Path`, name, duration, frame rate, timecode, resolution, audio layout, metadata, and timeline usage. Inspect the proposed full-resolution file outside DaVinci Resolve and prove it corresponds frame-for-frame to the proxy. After linking, search by the full-resolution basename rather than assuming the old proxy name still resolves. Use `media info` to confirm the new full-resolution `File Path` and resolution plus the old low-resolution path in `Proxy Media Path`; also inspect representative timeline occurrences for alignment, audio, and timecode continuity.

## Public arguments and options

- `CLIP` (required) — Media Pool clip name
- `PATH` (required) — Full-resolution media path
- `--dry-run/-n` (optional, default: `false`) — Show what would happen without making changes
- `--json/-j` (optional, default: `false`) — JSON output

## Boundaries and gotchas

- CutAgent CLI does not check existence, file type, compatibility, duration, frame rate, or timecode before mutation.
- `media proxy --unlink` removes the proxy association from the now-full-resolution item; it is not documented by this command as a reversal back to the proxy-only identity.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent media proxy link-fullres --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
