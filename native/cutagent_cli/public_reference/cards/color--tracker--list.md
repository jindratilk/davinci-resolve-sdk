# `color tracker list`

Syntax: `cutagent color tracker list [--clip VALUE] [--comp VALUE]`

## Search terms

- list Fusion trackers
- inspect clip trackers
- find tracker tool names
- show active tracking chain
- detect orphaned trackers
- check tracker mask order
- see trackers on current clip
- tracker connectivity readback
- enumerate clip-attached Trackers
- verify tracker attached to grade

## What it does

List clip-attached Fusion trackers.

## Do not use when

Use `color comp doctor` for validity errors/warnings and main image-pipe diagnostics. Use `color tracker add` only after this list confirms that a suitable tracker is absent.

## Preflight and readback

Before a tracker mutation, list with an explicit clip and comp wherever possible and save every returned name/order/orphan flag. Pair it with `color mask inspect` so the non-Tracker tools that account for global order are visible. Confirm the target clip separately if names repeat on the timeline; omission targets the current item.
After add/attach/detach/repair/track operations, list again and compare tool count, names, active status, MediaIn status and global order. Export the comp or inspect Tracker inputs/keyframes for requested centers and tracking results, because this listing cannot verify either.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- A missing/out-of-range comp and a comp with zero Trackers are distinct outcomes.
- Duplicate names can make an explicit `--clip` less precise than it appears.

## Examples

- `cutagent color tracker list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
