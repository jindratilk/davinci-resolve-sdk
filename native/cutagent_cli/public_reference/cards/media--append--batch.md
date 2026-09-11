# `media append batch`

Syntax: `cutagent media append batch [--batch VALUE] [--input VALUE] [--batch-json VALUE] [--allow-partial]`

## Search terms

- batch append Media Pool clips
- place many clips at exact frames
- append multiple source ranges
- build timeline from JSON edit list
- add clips across named timelines
- preflight bulk timeline placement
- append media by path or ID
- create many A1 or V1 items
- rename timeline items during append
- partial batch media placement

## What it does

Append multiple media pool items after checking every item.

## Do not use when

Use `media append` for one straightforward item. Use `media create-timeline` for a simple end-to-end stringout with no exact placement. Do not use `--allow-partial` when every requested edit must be all-or-nothing; it intentionally applies valid plans despite preflight errors.

## Preflight and readback

List target timelines/start frames/tracks/items and exact-search every media target. Build one JSON input with explicit folder/path or ID when names can collide, source ranges, record domain, and target timeline. Independently inspect each target track and confirm the originally active timeline was restored.

## Public arguments and options

- `--batch` (optional) — JSON batch file
- `--input` (optional) — JSON batch file alias
- `--batch-json` (optional)
- `--allow-partial` (optional, default: `false`) — Apply valid entries even when some entries fail preflight

## Boundaries and gotchas

- Exactly one of `--batch`, `--input`, or `--batch-json` is required.
- JSON may be a raw array or an object containing `entries`, `items`, `segments`, `updates`, or `batch`; every element must be an object.
- Only one record selector may appear per entry.

## Examples

- `cutagent media append batch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
