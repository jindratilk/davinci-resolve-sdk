# `multicam strip-embedded-audio`

Syntax: `cutagent multicam strip-embedded-audio [--multicam-name VALUE] [--media-id VALUE] [--sequence-id VALUE] [--allow-missing-audio] [--force]`

## Search terms

- remove multicam embedded audio
- preserve multicam video tracks
- allow missing multicam audio
- destructive multicam audio cleanup

## What it does

Remove CutAgent audio tracks and items from a multicam sequence.

## Do not use when

Do not use this to mute a timeline mix, disable one audio angle, replace isolated audio, or remove an ordinary timeline audio track.
Do not rerun against an already stripped multicam unless `--allow-missing-audio` is intentional. Without it, zero audio tracks is an error.
The command still clears media-level audio fields and can report a change if either field remains populated.
Confirm the same project/multicam reopens, video angles remain usable, embedded audio is absent, and representative playback/render is correct.

## Preflight and readback

Run dry-run and review the uniquely resolved target, would-remove counts, preserved video counts, and whether media audio fields would be cleared. Require at least one preserved video track and item.

## Public arguments and options

- `--multicam-name` (optional)
- `--media-id` (optional)
- `--sequence-id` (optional)
- `--allow-missing-audio` (optional, default: `false`) — Allow no-op when embedded audio tracks were already removed
- `--force/-f` (optional, default: `false`)

## Boundaries and gotchas

- A missing target returns no candidates; an ambiguous name returns candidate IDs.
- Dry-run returns removal counts and current video preservation counts.
- Without `--allow-missing-audio`, no audio track is treated as already missing even if media audio fields remain populated.
- There is no `--folder` selector.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent multicam strip-embedded-audio --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
