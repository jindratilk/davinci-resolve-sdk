# `fairlight dynamics read`

Syntax: `cutagent fairlight dynamics read [--track VALUE]`

## Search terms

- inspect compressor parameters
- get gate threshold
- check limiter settings
- is compressor enabled
- is noise gate on
- show dynamics preset values
- get track dynamics state
- check limiter threshold

## What it does

Read current dynamics parameters.

## Do not use when

Do not use this to answer “what are the dynamics on A2?” or any other track-specific question. The command accepts no track/timeline selector and does not prove which sequence/track the offsets describe.
Use `fairlight dynamics set`, `enable` or `disable` only when an actual mutation is intended.
Do not use this as loudness, peak, gain-reduction, gate activity or limiter-hit measurement. Use loudness analysis/render inspection for acoustic outcomes.
Do not confuse it with `fairlight effect params "Dialogue Processor"` or clip/track plugin inspection.
Do not use raw attack/hold/release/ratio numbers as milliseconds or ratios.

## Preflight and readback

In a multi-timeline project, acknowledge that the command cannot bind its result to the active timeline.
Sanity-check booleans, thresholds and every nominal 0–100 field. Values outside expected ranges are evidence of version/offset mismatch, not exotic user settings.

## Public arguments and options

- `--track` (optional, default: `1`) — Audio track index (1-based)

## Boundaries and gotchas

- It does not mean the offsets contain valid current-version dynamics records.
- There is no range validation.
- It does not validate record IDs, duplicate values or default fields around each supposed parameter record.

## DaVinci Resolve editions

Free was not independently exercised for this card.

## Examples

- `cutagent fairlight dynamics read --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
