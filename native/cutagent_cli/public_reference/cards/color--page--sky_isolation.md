# `color page sky-isolation`

Syntax: `cutagent color page sky-isolation [CLIP_NAME] [--hue VALUE] [--saturation VALUE] [--luma VALUE] [--window-size VALUE] [--window-aspect VALUE] [--window-pan VALUE] [--window-tilt VALUE] [--window-opacity VALUE] [--softness VALUE] [--blur VALUE] [--clean-black VALUE] [--clean-white VALUE] [--track] [--track-direction VALUE] [--highlights VALUE] [--sky-saturation VALUE] [--sky-temperature VALUE] [--sky-tint VALUE] [--sky-contrast VALUE] [--sky-pivot VALUE] [--sky-shadows VALUE] [--sky-color-boost VALUE] [--sky-mid-detail VALUE] [--sky-hue VALUE] [--sky-lum-mix VALUE] [--slope VALUE] [--offset VALUE] [--power VALUE] [--max-changed-percent VALUE] [--max-bottom-fraction VALUE] [--min-changed-percent VALUE] [--min-max-channel-diff VALUE] [--min-mean-abs-diff VALUE]`

## Search terms

- recover blown-out sky
- darken only the sky
- isolate blue sky with qualifier
- keep sky correction off foreground
- add a soft top-of-frame sky window
- restore saturation in washed-out sky
- track a moving sky mask
- combine HSL key and linear Power Window
- local highlight recovery for sky
- cool and deepen an overexposed sky
- prevent sky grade from affecting ground
- proof-gated sky secondary

## What it does

Recover an overexposed sky through a proof-gated Color Page interface local custom edit.

## Do not use when

Use `color page qualifier-gui-hsl-set`, `qualifier-gui-matte-set`, and a Power Window command separately when the user wants control of an existing node or needs to inspect each mask stage before a correction. Use Magic Mask/object masking for irregular moving foreground occlusion that a full-width linear top window plus HSL key cannot isolate. Use `color page hdr-global-set` or primary highlight controls for a global highlight recovery that should affect the entire frame. Use `power-window-track` alone when a window already exists and only tracking is requested. Do not pass legacy `--slope`, `--offset`, or `--power`; this workflow explicitly rejects the old CDL path and accepts only its listed primary GUI-style controls.

## Preflight and readback

Visually inspect multiple frames across the clip—especially horizon edges, clouds, skin and moving foreground—because the built-in final proof samples one frame.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--hue` (optional, default: `"0,359"`) — Sky qualifier hue range in degrees or turns
- `--saturation/--sat-range` (optional, default: `"0,55"`) — Sky qualifier saturation range
- `--luma` (optional, default: `"45,100"`) — Sky qualifier luma range
- `--window-size/--size` (optional, default: `100.0`) — Linear Power Window Size GUI value
- `--window-aspect/--aspect` (optional, default: `100.0`) — Linear Power Window Aspect GUI value
- `--window-pan/--pan` (optional, default: `50.0`) — Linear Power Window Pan GUI value
- `--window-tilt/--tilt` (optional, default: `80.0`) — Linear Power Window Tilt GUI value; higher values target the top of frame
- `--window-opacity/--opacity` (optional, default: `100.0`) — Linear Power Window Opacity GUI value
- `--softness` (optional, default: `20.0`) — Power Window Soft 1-4 GUI value
- `--blur` (optional, default: `5.0`) — Qualifier matte blur
- `--clean-black` (optional, default: `5.0`) — Qualifier clean black
- `--clean-white` (optional, default: `5.0`) — Qualifier clean white
- `--track/--no-track` (optional, default: `false`)
- `--track-direction` (optional) — Power Window tracking direction when --track is enabled
- `--highlights` (optional, default: `-35.0`) — Sky recovery Highlights GUI value on the isolated node
- `--sky-saturation/--sat` (optional, default: `60.0`) — Sky recovery Saturation GUI value on the isolated node
- `--sky-temperature/--sky-temp` (optional) — Sky recovery Temp GUI value on the isolated node
- `--sky-tint` (optional) — Sky recovery Tint GUI value on the isolated node
- `--sky-contrast` (optional) — Sky recovery Contrast GUI value on the isolated node
- `--sky-pivot` (optional) — Sky recovery Pivot GUI value on the isolated node
- `--sky-shadows` (optional) — Sky recovery Shadows GUI value on the isolated node
- `--sky-color-boost` (optional) — Sky recovery Color Boost GUI value on the isolated node
- `--sky-mid-detail` (optional) — Sky recovery Mid/Detail GUI value on the isolated node
- `--sky-hue` (optional) — Sky recovery Hue GUI value on the isolated node
- `--sky-lum-mix` (optional) — Sky recovery Lum Mix GUI value on the isolated node
- `--slope` (optional) — Legacy DB CDL option; unsupported in the GUI workflow
- `--offset` (optional) — Legacy DB CDL option; unsupported in the GUI workflow
- `--power` (optional) — Legacy DB CDL option; unsupported in the GUI workflow
- `--max-changed-percent` (optional, default: `45.0`) — Fail if proof changes more than this percentage of frame pixels
- `--max-bottom-fraction` (optional, default: `0.45`) — Fail if changed pixels extend below this normalized frame height
- `--min-changed-percent` (optional, default: `0.01`) — Fail if proof changes fewer than this percentage of frame pixels
- `--min-max-channel-diff` (optional, default: `3`) — Fail if the strongest proof pixel changes by fewer than this many 8-bit channel levels
- `--min-mean-abs-diff` (optional, default: `0.2`) — Fail if the proof mean absolute channel difference is weaker than this 8-bit value

## Boundaries and gotchas

- The render “before” frame is captured only after node creation, qualifier/matte/window setup and optional tracking.
- It proves the final primary correction changes the already-isolated image; it does not compare the untouched clip with the complete sky-isolation result.
- This same preflight must pass before any full workflow claim.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent color page sky-isolation --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
