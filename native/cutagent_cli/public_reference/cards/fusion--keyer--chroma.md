# `fusion keyer chroma`

Syntax: `cutagent fusion keyer chroma [--color VALUE] [--threshold VALUE]`

## Search terms

- add chroma key Fusion
- remove green screen Fusion
- ChromaKeyer node
- key blue screen Fusion
- key red background Fusion
- ChromaKeyer KeyColor ignored
- ChromaKeyer Threshold ignored
- Fusion ColorRange key
- chroma key false success
- chroma key dry-run mutates
- embedded ChromaKeyer partial mutation
- inline chroma keyer

## What it does

Add a chroma keyer inline.

## Do not use when

Do not use global dry-run as a preview.
Do not run against an ambiguous composition. There is no project, timeline, clip, track, record-frame, composition-index, tool, branch, or frame selector.
Do not use a simple named-color request when the source needs sampled colors, hue/luma ranges, despill, edge restoration, garbage/solid mattes, multiple keys, or tracked masks. The command exposes none of those controls.
Inspect the graph after every embedded failure.

## Preflight and readback

Before execution, inspect `status`, `fusion comp current`, and `fusion tool list`; export the graph and a representative source frame with visible key colors.
Validate that the color is one of green, blue, or red.
Studio external connected it between MediaIn and MediaOut; embedded Free left it orphaned after the wrapper exception.
Export the same frame and compare with baseline.
For cleanup, delete test keyers in reverse order and export the graph again.

## Public arguments and options

- `--color/-c` (optional, default: `"green"`) — Key color (green/blue/red)
- `--threshold/-t` (optional, default: `0.3`) — Threshold

## Boundaries and gotchas

- The command exposes no sampled color, channel ranges, luma range, SoftRange, spill suppression, fringe controls, matte blur/gamma/thresholds, invert, garbage/solid matte, or output mode.

## DaVinci Resolve editions

Studio external connected it between MediaIn and MediaOut; embedded Free left it orphaned after the wrapper exception.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion keyer chroma --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
