# `color qualifier list`

Syntax: `cutagent color qualifier list [--clip VALUE] [--comp VALUE]`

## Search terms

- list Fusion qualifiers
- show ChromaKeyer tools on clip
- inspect qualifier mask order
- find orphaned keyers
- check active chroma qualifiers
- see qualifier stack
- verify qualifier attach detach
- find ChromaKeyer names
- check Fusion qualifier comp
- list active and inactive qualifiers
- diagnose broken qualifier graph

## What it does

List clip-attached qualifier and keyer nodes.

## Do not use when

Use `color graph inspect` when the primary, main image pipe, windows, trackers, extra ColorCorrectors, complete mask chain or all tool types are needed. Use `fusion tool inputs/get` or `color comp export` to learn a ChromaKeyer's actual color range, matte controls, expressions or animation; this list exposes no key settings. Use `color qualifier attach` or `detach` only after this readback identifies an exact target and current active state. Do not treat it as visual matte validation; render/view the matte or resulting frame.

## Preflight and readback

Before listing without `--clip`, run `context` and put the playhead over the intended item. With a named target, confirm the current timeline and use a unique clip name. Know which Fusion composition index owns the grading graph. Before any subsequent attach/detach, export the comp if a broken/custom graph must be preserved.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- It does not inspect DaVinci Resolve Color page HSL qualifiers, other Fusion keyer types, or generic masks.
- The command does not run `color graph validate`.
- Matching still returns the first case-insensitive video name/basename across tracks, without a track/time disambiguator.
- The result rows do not echo the resolved clip name.
- `--comp` must be positive and refer to an existing comp.
- Reading does not require the Fusion page to be open.
- For direct `fusion tool` inspection, however, the correct timeline item/comp may need to be current on Fusion; do not conflate those target models.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color qualifier list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
