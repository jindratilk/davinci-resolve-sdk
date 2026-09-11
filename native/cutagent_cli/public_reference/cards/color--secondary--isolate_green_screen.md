# `color secondary isolate-green-screen`

Syntax: `cutagent color secondary isolate-green-screen [--clip VALUE] [--threshold VALUE] [--track] [--comp VALUE]`

## Search terms

- isolate green screen for grading
- create green chroma qualifier
- restrict ColorCorrector to green
- add green-screen secondary
- key green background in Fusion grade
- make green isolation mask
- add tracked green qualifier
- create ChromaKeyer for green
- grade only green-screen area
- wrap green key with tracker
- set up green chroma mask
- build green-screen Fusion secondary

## What it does

Create a green-screen isolation secondary.

## Do not use when

Use Fusion keyer/compositing commands when the goal is transparent foreground extraction rather than masking a ColorCorrector. Use `color secondary create --qualifier-color blue|red` for other friendly tokens, subject to the same input bug. Use `color tracker` tracking commands after setup when the key/mask must follow motion; `--track` here only creates a Tracker. Use `color primary set` to define the correction to be gated.

## Preflight and readback

Before running, inspect and export the comp, list existing qualifiers/trackers, and determine whether adding a default ChromaKeyer to a single global primary mask chain is acceptable. Use dry-run to validate threshold/target, but independently confirm actual ChromaKeyer input IDs for the installed DaVinci Resolve. If tracking is requested, choose the correct starting frame; note that this wrapper fixes the pattern center to the middle and exposes no direction/range.
Afterward, identify the exact new names from `created`, inspect the full graph rather than just the returned target rows, and read/export the ChromaKeyer's real color-range inputs. Verify an actual green matte before applying a primary adjustment. For `--track`, inspect tracker points and then explicitly execute tracking over the shot. Render the result at multiple frames. Check pre-existing mask order because the new tools can reorder/reconnect the entire existing stack. On any later-stage failure, look for partially retained ChromaKeyer/Tracker tools.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--threshold` (optional, default: `0.3`) — Qualifier threshold
- `--track` (optional, default: `false`) — Wrap the isolation with a tracker
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- There is no hue/range control, eyedropper sample, matte refine, spill suppression, window, custom tracker center or key inversion.
- A new tracker is not semantically paired with only the new keyer.
- Dry-run is genuinely non-mutating here.
- It performs request validation only and returns green, threshold, track and fixed center; it does not connect or prove the clip/comp/keyer compatibility.
- It does not inspect key parameters, run tracking, evaluate matte quality or render pixels.
- The wrapper does not advertise those extra objects in its name.
- Named target matching uses the first case-insensitive clip name/basename across tracks and cannot disambiguate duplicates.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color secondary isolate-green-screen --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
