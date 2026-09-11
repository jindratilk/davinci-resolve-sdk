# `timeline overlay-stack insert`

Syntax: `cutagent timeline overlay-stack insert [--spec VALUE] [--spec-json VALUE]`

## Search terms

- multi-layer Fusion graphic
- Text+ setting stack
- image setting overlay
- candidate video track stack
- shared overlay background
- JSON overlay specification
- lower third stack

## What it does

Insert a layered overlay.

## Do not use when

Do not use it when atomic all-or-nothing behavior is required.
Do not blindly accept a shifted layout.

## Preflight and readback

Before execution, save/checkpoint the project; inspect the exact timeline/start frame/FPS, every candidate and background track, padded collisions, source/template/image files, unique Media Pool matches, holder/template compatibility, Fusion tool/input names, and marker color/duration.
In DaVinci Resolve verify tracks, exact start/end/duration, z-order, text/style, images/transforms, Fusion graphs, source content, marker, neighboring clips, playback, and render output.

## Public arguments and options

- `--spec` (optional) — Overlay stack JSON spec path
- `--spec-json` (optional) — Inline overlay stack JSON spec

## Boundaries and gotchas

- Supply exactly one of `--spec PATH` or `--spec-json JSON`.
- Input must decode to a JSON object.
- A spec can target `timeline`; otherwise an active timeline is required.
- `layout` is required.
- The planner checks only selected layout tracks, not an optional background track.
- Dry-run does not create tracks, resolve Media Pool assets, test templates/images, import Fusion graphs, apply content, add markers, or exercise cleanup.
- Each layer offset must exist in every candidate stack, not just the selected one.
- Duplicate roles and duplicate output names are not rejected.
- Optional `position` must be an object; `x`/`y` convert to floats.
- Media resolution is exact and must produce one Media Pool item.
- Planning does not check that the template file exists.
- After setting insertion, the command must find the timeline item by track, record frame, and name for follow-up updates.
- Planning does not check that the image exists.
- A shared match can be reused without proving it covers the full overlay range.
- That metadata does not represent independent visual/render verification or exhaustive duration/content checks.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline overlay-stack insert --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
