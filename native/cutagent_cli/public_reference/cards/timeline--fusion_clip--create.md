# `timeline fusion-clip create`

Syntax: `cutagent timeline fusion-clip create CLIPS...`

## Search terms

- create Fusion clip
- combine timeline clips in Fusion
- Fusion clip from named items
- convert clips to Fusion clip
- multi-clip Fusion composition

## What it does

Create a Fusion clip from timeline items.

## Do not use when

Do not use it when clip identity is ambiguous, exact track/record-frame targeting is required, or items must remain separate. This command accepts names only and can structurally replace/group the supplied items.
Do not assume the command will trim, align, sort, or validate gaps/overlaps/tracks.

## Preflight and readback

Before execution, checkpoint the project and inspect the active timeline. Resolve every clip name to an exact item, verify track/type/order/bounds/links, and confirm that DaVinci Resolve can create the intended Fusion clip from that item set.

## Public arguments and options

- `CLIPS` (required, repeatable) — Timeline clip names

## Boundaries and gotchas

- At least one positional clip name is required by the CLI.
- An active timeline is required.
- Dry-run does not echo names or resolved identities.
- Matching first attempts exact text, then case-insensitive text/basename.
- Duplicate names are not rejected as ambiguous; the first matching item is selected.
- The command does not sort by timeline position.
- It does not require items to be contiguous, on the same track, or video-only before calling DaVinci Resolve.
- It does not capture input descriptors or pre-mutation timeline state.
- It does not re-enumerate the timeline to prove that source items were replaced or grouped exactly once.
- It does not inspect the created Fusion composition or verify rendered pixels.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `MISSING_ARGUMENT`

## Examples

- `cutagent timeline fusion-clip create --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
