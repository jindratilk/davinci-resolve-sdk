# `fusion comp delete`

Syntax: `cutagent fusion comp delete [INDEX] [--clip VALUE] [--force]`

## Search terms

- delete Fusion composition
- remove Fusion comp from clip
- detach Fusion composition
- delete comp by index
- remove current clip Fusion graph
- strip Fusion from timeline clip
- delete last Fusion comp
- remove secondary Fusion composition
- clear Fusion comp from named clip
- get rid of Fusion effect composition
- remove Composition1 from clip
- delete one of multiple Fusion comps

## What it does

Delete a Fusion composition from the current and named timeline clip.

## Do not use when

Use `clip fusion delete INDEX --clip NAME --track N --record-frame POSITION` when duplicate clip names or overlapping items require an explicit video-track and record-domain selector.
Use `timeline delete NAME --force` only when the entire timeline and all of its clips should be removed. Composition deletion is scoped to one timeline item.
Use a project/timeline checkpoint or duplicate when the last-comp reconstruction could lose unsupported timeline-item state. The operation has no inverse command and cannot recreate the deleted node graph.
Do not target a clip by name alone when names are duplicated and the wrong match would be destructive. Switch/use `clip fusion delete` with track and record-frame selectors instead.

## Preflight and readback

Before deletion, verify the active project and timeline. Run `clip list` for the target track, then `clip fusion list` with the most specific available selectors. Record the one-based index/name mapping and inspect/export the target graph if any recovery may be needed.
Run `fusion comp delete INDEX --clip NAME --dry-run` to inspect the requested action, but do not treat its success as target validation: dry-run deliberately avoids DaVinci Resolve and does not confirm that the clip or index exists.
Before deleting the only comp, stop playback/render, clear all Fusion render-completion dialogs, leave the Fusion page, and move the playhead outside the target clip.
After a multi-comp delete, repeat `clip fusion list` and prove that count decreased by one and that the surviving names/indexes are correct.
For visually meaningful clips, inspect/render representative frames after recreation. A zero comp count does not prove that every non-Fusion clip property, linked item, marker, speed state, audio relation, and grade survived.

## Public arguments and options

- `INDEX` (optional, default: `1`) — Composition index
- `--clip` (optional) — Clip name (current clip when omitted)
- `--force/-f` (optional, default: `false`) — Skip confirmation

## Boundaries and gotchas

- The index is one-based.
- Omitting it can delete the only or primary composition.
- `--clip` has no track or position selector.
- Duplicate clip names can resolve ambiguously; use `clip fusion delete` when identity requires track/record position.
- Candidate-name fallbacks can be risky when name-list/attrs are incomplete; verify the post-delete names, not only count.
- Only a fixed property allowlist is captured/restored.
- Use an isolated duplicate/checkpoint for important last-comp removals.

## Stable public error codes

- `API_CALL_FAILED`
- `CONFIRMATION_REQUIRED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion comp delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
