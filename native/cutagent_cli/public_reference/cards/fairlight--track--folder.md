# `fairlight track folder`

Syntax: `cutagent fairlight track folder TRACKS... [--name VALUE] [--collapse]`

## Search terms

- create Fairlight folder track
- group audio tracks into folder
- collapse Fairlight tracks
- put dialogue tracks in a folder
- organize A1 and A2 under folder
- Add Tracks to New Folder
- make audio track group
- create composite Fairlight track
- folder-level mute and solo
- nest Fairlight tracks
- open collapsed audio folder
- rename Fairlight folder track

## What it does

Create a Fairlight folder track.

## Do not use when

Do not use this command expecting a best-effort folder creation.
Use `fairlight track duplicate` when the actual request is to clone an audio track; a duplicate is a separate normal track, not a collapsible folder containing members.
Use `fairlight add` or `timeline track add` when the goal is simply to add audio tracks. Use track rename, mute/unmute, enable/disable, lock/unlock or track-color commands when the desired change applies to ordinary tracks individually.
Do not substitute `fairlight mute`/`unmute` for folder visibility or collapse. Folder collapse is Fairlight layout state, while mute changes audible state.
Do not model a Fairlight folder as a bus, VCA, group, compound clip or timeline bin. Folder tracks are a DaVinci Resolve 21 Fairlight timeline/mixer feature with membership, collapse, folder-level solo/mute and nesting semantics; those other constructs have different routing and editing behavior.

## Preflight and readback

Before deciding on the command, confirm that the user specifically means DaVinci Resolve 21 Fairlight folder tracks rather than buses, VCAs or ordinary track organization. Run `project info`, `timeline info` and `fairlight tracks` to identify the intended member tracks for a manual handoff; this command itself will not do that validation.
After the user creates a folder in the GUI, verify it visually on the Fairlight page: member tracks appear under the folder strip, collapse/open works, and deleting the folder restores the original track positions. CutAgent CLI has no reliable folder-list or membership readback, so ordinary `fairlight tracks` output cannot prove folder identity or nesting.

## Public arguments and options

- `TRACKS` (required, repeatable) — Audio track indices to place in a Fairlight folder
- `--name` (optional) — Requested Fairlight folder track name
- `--collapse/--open` (optional, default: `false`) — Requested initial folder collapsed state

## Boundaries and gotchas

- The command says the automation route is unsupported; it does not claim that the product feature is absent.
- At least two positional integers are required.
- Once there are two entries, the command does not check active-project state, track count, index existence, ordering, contiguity or uniqueness.
- `--collapse` changes only the echoed request to `collapse:true`; `--open` changes it to false.
- `--name` is not validated against existing folder names because no folder operation is attempted.
- The command must not be “fixed” by blindly invoking guessed methods.
- Because CLI readback is unavailable, post-GUI verification must remain visual.
- Do not report success merely because ordinary audio tracks still appear in `fairlight tracks`.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight track folder --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
