# `color primary get`

Syntax: `cutagent color primary get [--clip VALUE] [--comp VALUE]`

## Search terms

- inspect ColorCorrector values
- get clip-attached color correction
- check Fusion gain gamma saturation
- see primary ColorCorrector settings
- verify color primary set
- inspect master gain and gamma
- does clip have a Fusion primary
- check clip Fusion grade state
- get primary grade without changing it

## What it does

Read primary Fusion color-corrector state from the clip.

## Do not use when

Use `color graph inspect` when tool ordering, main-pipe connectivity, extra ColorCorrectors, masks, qualifiers, trackers or orphaned tools matter. Use `fusion tool get`/Fusion inspection for arbitrary inputs on a specifically named ColorCorrector rather than the first one. Use `color primary set` only when the user wants to create or change this Fusion primary. Use `color inspect`, frame export or a render comparison to judge the visible result; numeric tool inputs do not prove what reaches MediaOut.

## Preflight and readback

If `--clip` is omitted, first run `timeline current-item` or `context` and make sure the playhead is over the intended video; do not rely on the output's null `clip` field to identify it.
For a setter verification, compare every requested field to this readback and also run `color graph validate`/`color graph inspect` to prove the tool is connected to the expected main pipe.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- Agents must not collapse those into the same state.
- `--comp` is 1-based at the CLI and must be positive.
- It does not report extra ColorCorrectors.
- When `--clip` is omitted it is `null` even though a current item was read.
- Case-insensitive or basename matching can also resolve a differently spelled name while echoing the user's input.
- Named resolution scans video tracks in ascending order and returns the first exact/case-insensitive name or basename match; duplicate clip names have no disambiguating track/record-frame options here.
- Without `--clip`, resolution first asks for the current video item and then searches under the playhead.
- This getter does not validate graph connectivity.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent color primary get --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
