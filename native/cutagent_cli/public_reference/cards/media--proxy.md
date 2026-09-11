# `media proxy`

Syntax: `cutagent media proxy [--generate] [--link VALUE] [--unlink] [--dry-run] [--json]`

## Search terms

- attach proxy file to source clip
- link lightweight editing media
- unlink proxy from Media Pool item
- remove proxy association
- generate proxy media
- generate optimized media
- switch clip back to original media
- use low resolution copy for editing

## What it does

Manage media pool proxy media for a clip.

## Preflight and readback

Before linking, independently inspect the proposed proxy file and ensure duration, frame rate, timecode, audio layout, and picture geometry correspond to the full-resolution source. After linking, require `media info` to show the expected proxy resolution and exact `Proxy Media Path`; after unlinking, require `Proxy: None` and an empty proxy path while confirming the original `File Path` is unchanged.

## Public arguments and options

- `--generate` (optional, default: `false`) — Generate proxy/optimized media
- `--link` (optional) — Link proxy media path
- `--unlink` (optional, default: `false`) — Unlink proxy media
- `--dry-run/-n` (optional, default: `false`) — Show what would happen without making changes
- `--json/-j` (optional, default: `false`) — JSON output

## Boundaries and gotchas

- The positional syntax is a compatibility path parsed from otherwise-extra callback arguments: `media proxy CLIP --link PATH`.
- Help displays the action options but does not display the required positional clip.
- The hidden `--name CLIP` form also exists; do not infer that the clip is optional.
- Exactly one of `--generate`, `--link`, and `--unlink` is required.
- `--link` does not validate that the path exists, is a file, or matches the source before passing it to DaVinci Resolve.
- `--unlink` only removes the Media Pool association.
- It does not delete the proxy file from storage.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent media proxy --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
