# `fairlight clip slip`

Syntax: `cutagent fairlight clip slip [--timeline VALUE] [--item-id VALUE] [--track VALUE] [--start-frame VALUE] [--current-end-frame VALUE] [--name VALUE] [--source-start-frame VALUE] [--delta VALUE] [--allow-linked-audio-only] [--include-linked-video]`

## Search terms

- slip audio inside timeline clip
- change source in without moving clip
- shift clip content under fixed edit
- adjust Fairlight source offset
- use later audio while keeping timeline range
- use earlier source samples
- change audio clip source In
- correct sync inside fixed audio edit
- move waveform under clip boundaries
- replace clip content timing without ripple
- preserve record start and duration while slipping

## What it does

Update Fairlight audio source timing.

## Do not use when

Use `fairlight clip move` or `nudge` when the audio occurrence itself must change record position. Slip deliberately leaves record start/end fixed.
Use `fairlight clip trim` when an edge/duration must change. Slip preserves both edges and exposes different source content beneath them.
Slip stays on the existing source and only changes its source offset.
Do not use this route for linked non-video/complex groups, multi-channel source-edge remapping, transition-aware reflow or selection-range slips.
Do not slip linked audio alone unless desynchronization is intentional. Prefer `--include-linked-video`; reserve `--allow-linked-audio-only` for explicit audio-only work.

## Preflight and readback

Before mutation, record the exact item ID, audio track, absolute timeline start/end/duration, current source In/left offset, available right offset, source media type, links and any transition covering the item.
For public operation, prove companion membership from DaVinci Resolve's reported link relationship and bind every companion to one stable exact item identity; do not infer links from coincident ranges or names. After reopen, mandatory verification checks unchanged record bounds, requested source timing, link membership, and unchanged surrounding items. Required verification must succeed; otherwise the operation is automatically rolled back to the prior project state. If automatic recovery cannot complete, JSON identifies possible mutation and required manual recovery.
Re-run `source-range`. Audition or render the isolated changed range. For a temporary slip, apply the exact inverse delta and compare the restored render to baseline.

## Public arguments and options

- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--item-id` (optional)
- `--track/--track-index` (optional, default: `1`) — Audio track index for selector
- `--start-frame` (optional) — Current audio item start in record-domain frames/time
- `--current-end-frame` (optional) — Current audio item end for stricter selection
- `--name` (optional) — Current timeline item name for stricter selection
- `--source-start-frame/--source-in-frame/--source-in` (optional) — New source In frame/time for the selected audio item
- `--delta/--slip` (optional) — Signed source slip amount, e.g. 12f or -0.5s
- `--allow-linked-audio-only` (optional, default: `false`)
- `--include-linked-video` (optional, default: `false`)

## Boundaries and gotchas

- `--source-start-frame` and `--delta` are mutually exclusive, and one is mandatory.
- Source positions cannot be negative.
- `--source-in 1f` means source frame 1, not timeline frame 1.
- Some media types without finite audio/video source bounds do not receive right-extent validation.
- It does not inspect waveform content or audible sync.
- Timeline clip overlaps are irrelevant because the item does not move, but existing audio layering can make audible verification ambiguous; isolate the target range.
- Without item ID, matching is limited to the stated 1-based audio track and accepts case-insensitive display/source aliases; multiple matches fail.
- With item ID, `--start-frame`, `--current-end-frame` and `--name` cannot be combined.
- Explicit `--timeline` switches to that timeline and leaves it active after reopen.

## Examples

- `cutagent fairlight clip slip --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
