# `fairlight loudness analyze`

Syntax: `cutagent fairlight loudness analyze [--standard VALUE]`

## Search terms

- analyze timeline loudness
- measure integrated LUFS
- run EBU R128 analysis
- check ATSC A/85 loudness
- get true peak
- scan Fairlight mix loudness
- loudness report from DaVinci Resolve
- measure programme loudness
- inspect short-term loudness
- export loudness analysis results
- check broadcast audio compliance
- calculate BS.1770 loudness

## What it does

Check Fairlight loudness analysis availability.

## Do not use when

When an actual measurement is required, render the exact audible timeline/stem with `fairlight export audio` or the explicit render workflow, verify the rendered file, then run a trusted external BS.1770/EBU R128 analyzer on that file. Do not substitute `fairlight loudness normalize`: the public normalize command is also intentionally unsupported.

## Preflight and readback

If the user needs measurements, inspect the current timeline, audible track/bus state, duration and delivery standard, then proceed directly to a rendered-file analysis workflow.
Do not retry with another standard: the failure is route-wide, not caused by the standard string. If continuing externally, verify the rendered file's channel layout, sample rate, duration and audible content before trusting the analyzer's LUFS/true-peak result.

## Public arguments and options

- `--standard` (optional) — Loudness standard, e.g. EBU R128 or ATSC A/85

## Boundaries and gotchas

- A closed DaVinci Resolve instance, no open project, a different active timeline, or a modal dialog does not change this command's result.
- `--standard` is informational only.
- The command does not change the project, selection, playhead, page, render queue, files, or meter state.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight loudness analyze --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
