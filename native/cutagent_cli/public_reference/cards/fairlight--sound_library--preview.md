# `fairlight sound-library preview`

Syntax: `cutagent fairlight sound-library preview [QUERY] [--clip-id VALUE] [--file-id VALUE] [--result-index VALUE] [--sync-to-playhead] [--database VALUE]`

## Search terms

- preview Sound Library sound
- listen before inserting
- play indexed SFX
- hear a library clip
- preview Foley result
- listen to Sound Library item
- play library audio without timeline edit
- sync sound preview to playhead
- preview by clip ID
- preview by file ID
- check how a sound effect sounds
- stop Sound Library preview

## What it does

Preview a Fairlight Sound Library result.

## Do not use when

Use the visible Fairlight Sound Library panel when the request is genuinely to hear a sound without changing the edit. Panel audition, monitoring output, stop control and synchronized preview remain manual DaVinci Resolve interactions.
Use an external audio player only when the exact file path has already been obtained and DaVinci Resolve panel routing/synchronization is irrelevant. This command neither supplies nor validates that path.
The unsupported boundary covers status and stop operations as well as playback start.

## Preflight and readback

For a useful manual preview workflow, first run `sound-library search` in the correct project/user scope, disambiguate by ID/path, confirm the media is online, then use DaVinci Resolve's Sound Library panel. Check monitoring level and output before playback, and explicitly stop the panel preview afterward.
Treat that as a separate mutating operation and verify the new timeline item and playhead.
After any `preview` CLI invocation, expect no state delta.

## Public arguments and options

- `QUERY` (optional) — Search query or known library result name to audition
- `--clip-id` (optional)
- `--file-id` (optional)
- `--result-index` (optional) — 1-based result index when the selector matches multiple rows
- `--sync-to-playhead/--no-sync-to-playhead` (optional, default: `false`) — Request Sound Library panel sync-preview behavior when available
- `--database/--db` (optional, default: `"project"`) — Sound Library DB scope: project/current-project or user/local-database

## Boundaries and gotchas

- A plausible name and a fabricated `--clip-id` produce the same unsupported error.
- No selector is required.
- `--result-index` must be at least 1 at CLI parsing time, but a valid number is never applied to a result list.
- `--sync-to-playhead` changes only the echoed request boolean.
- `--dry-run` does not turn the blocker into a successful plan.
- Do not collapse them when diagnosing which user-facing spelling was invoked.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight sound-library preview --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
