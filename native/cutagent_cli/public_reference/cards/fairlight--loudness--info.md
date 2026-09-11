# `fairlight loudness info`

Syntax: `cutagent fairlight loudness info [--limit VALUE]`

## Search terms

- check loudness analysis storage
- inspect audio meter alignment level
- find EBU R128 project data
- check whether loudness results are saved
- distinguish meter settings from measurements

## What it does

Runs the public `fairlight loudness info` CutAgent command.

## Do not use when

Do not use this command to obtain Integrated LUFS, loudness range, momentary/short-term values, true peak, meter movement, a graph, or broadcast pass/fail.
Do not use it to normalize audio or change the meter standard/alignment.

## Preflight and readback

Before running, confirm the intended named project is active. An active timeline is optional, but capture it if the agent later needs to relate any candidate rows to a particular edit.

## Public arguments and options

- `--limit` (optional, default: `20`)

## Boundaries and gotchas

- It does not validate values, freshness, standard, timeline ownership, or whether DaVinci Resolve currently uses that storage.
- Changing `--limit` from 1 to 5 changed no result because row limit cannot create missing data.
- It does not require a current timeline.

## Examples

- `cutagent fairlight loudness info --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
