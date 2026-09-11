# `fairlight ensure-tracks`

Syntax: `cutagent fairlight ensure-tracks --count VALUE [--track-type VALUE] [--timeline VALUE] [--allow-existing]`

## Search terms

- ensure minimum mono audio tracks
- add missing stereo tracks
- create Fairlight track layout
- make two dialogue tracks
- add 5.1 film audio tracks
- create adaptive audio tracks
- guarantee track format count
- provision empty audio lanes
- add LCR or surround tracks
- prepare timeline audio track count

## What it does

Ensure enough audio tracks.

## Do not use when

Do not use this command when every existing audio track should be converted to stereo; that destructive subtype rewrite is the distinct default behavior of `fairlight ensure-stereo-tracks`. Use `fairlight track-format set` when changing the format of a particular existing empty track. Use `fairlight delete` for excess tracks. Do not use `--no-allow-existing` as a normal “ensure minimum” mode; it means create the requested number of new tracks even when matching tracks already exist.

## Preflight and readback

Run `fairlight tracks` on the intended timeline and count formats, not merely total lanes. Confirm that downstream track indices can tolerate new tracks being appended. Afterward, rerun `fairlight tracks`, require at least the requested matching subtype count, confirm each new lane is empty and at the end, and check that the originally active timeline was restored when `--timeline` targeted another one.

## Public arguments and options

- `--count` (required) — Minimum number of matching audio tracks to ensure
- `--track-type` (optional, default: `"stereo"`) — Audio format: mono, stereo, lcr, 5.1film, 7.1film, adaptive1..adaptive36
- `--timeline` (optional) — Optional target timeline name
- `--allow-existing/--no-allow-existing` (optional, default: `true`) — Count existing tracks with matching format when format readback is available

## Boundaries and gotchas

- `--count` is the number of matching-format tracks, not total audio tracks.
- Existing credit is available only when at least one track row exposes a `format`.
- New tracks are always appended because this command does not expose an index.
- Track-number-based workflows must account for the added tail lanes.
- `adaptive` is the only legacy alias; unsupported abbreviations fail validation.
- The command does not save or reopen the project.
- A named target timeline is restored only after the normal success path.

## Examples

- `cutagent fairlight ensure-tracks --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
