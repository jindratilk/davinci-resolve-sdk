# `color secondary create`

Syntax: `cutagent color secondary create [--clip VALUE] [--window VALUE] [--qualifier-color VALUE] [--threshold VALUE] [--track] [--pattern-center VALUE] [--comp VALUE]`

## Search terms

- create Fusion secondary grade
- combine window qualifier tracker
- make tracked color isolation
- build masked ColorCorrector
- add rectangle color secondary
- add ellipse and chroma key
- create localized Fusion grade
- restrict grade with key and tracker
- build power-window style Fusion mask
- create subject mask stack
- set up tracked qualifier workflow
- compose secondary correction graph

## What it does

Compose a secondary grade from window, qualifier, and optional tracker.

## Do not use when

Use `color window rectangle`/`ellipse` when custom center, width, height or softness is needed. Use `color window polygon` for polygon points; this wrapper explicitly rejects polygon. Use `color secondary tracked-window` for the narrower window+tracker recipe, `subject-isolation` for its fixed ellipse+tracker recipe, and `isolate-green-screen` for its named qualifier recipe, while still checking their shared Fusion limitations. Use `color primary set` after this command to create the actual Fusion correction. Do not use this wrapper on a bespoke Fusion graph unless whole-graph canonicalization is acceptable.

## Preflight and readback

Before creation, inspect/export the target comp, identify all existing windows/qualifiers/trackers/primaries, and confirm the fixed category order plus neutral primary are intended. Decide which subset is needed; at least one of window, qualifier or tracker is required. For keying, discover the actual ChromaKeyer controls in the installed DaVinci Resolve rather than trusting the friendly color/threshold output. For tracking, choose a meaningful initial frame/pattern center and capture the current playhead/comp frame separately.
Apply the intended primary color adjustment, execute the tracker over the necessary range, inspect matte/key edges, and render representative frames. Verify that any pre-existing helpers were not unintentionally incorporated/reordered.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--window` (optional) — rectangle|ellipse
- `--qualifier-color` (optional) — green|blue|red
- `--threshold` (optional, default: `0.3`) — Qualifier threshold
- `--track` (optional, default: `false`) — Wrap the secondary with a tracker
- `--pattern-center` (optional, default: `"0.5,0.5"`) — Tracker pattern center X,Y
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- If qualifier or tracker creation fails, an earlier window/qualifier remains; final validation failure does not roll the whole recipe back.
- `--track` does not specifically wrap only the newly created window/qualifier in an isolated branch; it joins the single primary EffectMask stack.
- An invalid string rejects a window-only or qualifier-only request despite that center being unused.
- Threshold is range/finite validated only when `--qualifier-color` is present.
- At least one of `--window`, `--qualifier-color`, or `--track` must be selected.
- The command does not infer a default secondary recipe.
- Only rectangle and ellipse are accepted here.
- It does not compare window geometry, qualifier controls, tracker centers, track data or pixels.
- Dry-run is correctly non-mutating and does not connect.
- Named clip resolution chooses the first case-insensitive name/basename match across video tracks; no track/time disambiguation is available.

## Examples

- `cutagent color secondary create --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
