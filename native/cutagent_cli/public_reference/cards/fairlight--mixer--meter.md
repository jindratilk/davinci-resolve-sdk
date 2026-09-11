# `fairlight mixer meter`

Syntax: `cutagent fairlight mixer meter [--track VALUE] [--bus VALUE] [--include-peak-hold]`

## Search terms

- check audio track peak level
- inspect A1 meter dBFS
- see if audio is clipping
- get mixer peak hold
- monitor audio level during playback
- measure track signal level
- query Bus 1 meter
- check mixer clip indicator
- stream audio meters

## What it does

Check Fairlight mixer metering availability.

## Do not use when

For an actual peak, true-peak, RMS, or LUFS measurement, render/export the relevant audio and analyze the resulting file with a suitable audio meter. For immediate visual feedback during playback, use DaVinci Resolve's visible Fairlight meters and report the observation as manual GUI evidence.

## Preflight and readback

If the workflow needs a real measurement, first identify the exact timeline range, track/bus routing, fader/automation state, and whether the requested metric is sample peak, true peak, RMS, or integrated/short-term LUFS. Render a deterministic audio file, measure it externally, and retain the rendered artifact and meter report.

## Public arguments and options

- `--track/-t` (optional) — Audio track index
- `--bus` (optional) — Bus/main output name
- `--include-peak-hold/--no-peak-hold` (optional, default: `true`) — Request peak-hold values when available

## Boundaries and gotchas

- `--bus` accepts arbitrary text.
- `--include-peak-hold` defaults to true, but it is request metadata only.
- Opening DaVinci Resolve Studio does not alter the public command's hardwired path.
- It is not wired to this CLI command, does not support peak hold, and must not be cited as this command's result.
- Agents must branch on the JSON error instead of treating the absence of meter data as silence or −∞ dBFS.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight mixer meter --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
