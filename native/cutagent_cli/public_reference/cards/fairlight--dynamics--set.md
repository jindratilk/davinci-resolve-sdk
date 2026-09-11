# `fairlight dynamics set`

Syntax: `cutagent fairlight dynamics set [--track VALUE] [--comp-threshold VALUE] [--comp-ratio VALUE] [--comp-knee VALUE] [--comp-mix VALUE] [--comp-enable] [--gate-threshold VALUE] [--gate-enable] [--lim-threshold VALUE] [--lim-enable]`

## Search terms

- set Fairlight compressor threshold
- change compressor ratio
- adjust dynamics mix
- enable or disable compressor
- set noise gate threshold
- turn Fairlight gate off
- set limiter threshold
- disable limiter
- edit compressor knee
- tune dialogue dynamics
- change compressor gate limiter settings
- set dynamics raw ratio

## What it does

Set individual dynamics parameters.

## Do not use when

Do not use this for one track or one timeline in a multi-timeline project.
Do not use this for make-up gain, attack, hold, release, gate range/ratio, limiter input-enable, per-band EQ, clip FX or bus processing.
Do not use dynamics values alone as loudness/compliance proof. Render and analyze actual signal behavior.

## Preflight and readback

Use a disposable single-timeline project for version qualification.
Convert intended displayed controls to their actual storage domain.
Render/audio-test compressor, gate and limiter action.

## Public arguments and options

- `--track` (optional, default: `1`) — Audio track index (1-based)
- `--comp-threshold` (optional) — Compressor threshold (dB, e.g. -20.0)
- `--comp-ratio` (optional)
- `--comp-knee` (optional) — Compressor knee (0-100)
- `--comp-mix` (optional) — Compressor mix (0-100)
- `--comp-enable/--comp-disable` (optional) — Enable/disable compressor
- `--gate-threshold` (optional) — Gate threshold (dB)
- `--gate-enable/--gate-disable` (optional) — Enable/disable gate
- `--lim-threshold` (optional) — Limiter threshold (dB)
- `--lim-enable/--lim-disable` (optional) — Enable/disable limiter

## Boundaries and gotchas

- In a multi-timeline project, parameters and unrelated sequence-model state from the arbitrary first row are cloned into every timeline, even when only one parameter was requested.
- `--comp-enable/--comp-disable`, `--gate-enable/--gate-disable` and `--lim-enable/--lim-disable` are independent optional booleans.
- It does not validate neighboring record IDs/default/type fields.
- Successful verification re-parses only the arbitrary first sequence and requested fields.
- It does not check every row, GUI controls, config, track identity or rendered audio.

## DaVinci Resolve editions

Free was not independently exercised for this card.

## Examples

- `cutagent fairlight dynamics set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
