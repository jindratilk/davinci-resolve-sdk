# `media matte list`

Syntax: `cutagent media matte list CLIP`

## Search terms

- list clip mattes
- inspect Media Pool matte paths
- show external mattes attached to clip
- find left right eye matte files
- audit clip matte associations
- verify matte import
- list alpha matte sources
- check whether clip has mattes

## What it does

List mattes attached to a media pool clip.

## Do not use when

Use `storage matte add` to attach new clip mattes and `media matte delete` to remove known paths. Do not use this output to infer which stereo eye owns each matte—the list does not include eye labels.

## Preflight and readback

Exact-search the target clip and retain folder/ID context. Run list before an add/delete operation to capture the complete path set, then rerun afterward and compare exact paths and count. Verify matte rendering/eye assignment separately in DaVinci Resolve because path presence alone does not prove the image is compatible or applied as intended.

## Public arguments and options

- `CLIP` (required) — Media Pool clip name

## Examples

- `cutagent media matte list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
