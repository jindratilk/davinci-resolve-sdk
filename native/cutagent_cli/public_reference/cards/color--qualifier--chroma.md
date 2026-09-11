# `color qualifier chroma`

Syntax: `cutagent color qualifier chroma [--clip VALUE] [--color VALUE] [--threshold VALUE] [--comp VALUE]`

## Search terms

- add chroma qualifier
- key green screen in Fusion
- create ChromaKeyer mask
- isolate green with a qualifier
- add blue screen keyer
- create red chroma key
- qualify a color in Fusion
- make ColorCorrector affect keyed pixels
- add clip-attached keyer
- create a chroma matte for grade
- attach ChromaKeyer to primary
- color-selective Fusion grade

## What it does

Add a chroma qualifier using Fusion ChromaKeyer.

## Do not use when

Use `color qualifier attach` to reconnect/reorder an already existing ChromaKeyer rather than creating a duplicate. Use `color qualifier detach` to stop one from affecting the primary without deleting it. Use `fusion keyer` commands when the goal is compositing transparency rather than restricting a Fusion ColorCorrector. Do not use this to refine matte edges, despill or tune actual ChromaKeyer ranges; none of those controls are exposed here.

## Preflight and readback

Before creation, inspect `color graph inspect` and `color qualifier list`, export the comp if it has custom wiring, and record every existing keyer name/order plus the first ColorCorrector. Confirm that adding a new composition/primary and canonicalizing all windows, qualifiers and trackers is acceptable. Validate that the desired color is one of the three tokens and threshold is finite in 0..1, while recognizing that validation does not prove those values can be written.
Do not accept returned `color`/`threshold` as readback. Inspect the full mask chain and main pipe for collateral rewiring, render the matte/output at representative frames, and tune a supported set of actual key controls.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--color` (optional, default: `"green"`) — Key color (green/blue/red)
- `--threshold` (optional, default: `0.3`) — Threshold
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- `--dry-run` is destructive.
- Color validation is strict after trimming/lowercasing: only `green`, `blue`, and `red` are accepted.
- Threshold must be finite and inclusive between 0.0 and 1.0.
- This command does not translate the friendly color/threshold request into those real controls.
- Multi-primary or branched Fusion comps can be visibly changed even though the command ostensibly only “adds a qualifier.”
- Clip names are trimmed and whitespace-only names are rejected.
- Their returned green/blue/red labels must not be interpreted as actual configured key colors.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color qualifier chroma --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
