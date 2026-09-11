# `color page white-balance-picker`

Syntax: `cutagent color page white-balance-picker [CLIP_NAME] --x VALUE --y VALUE [--radius VALUE] [--at VALUE] [--strength VALUE] [--output VALUE]`

## Search terms

- white balance from a gray patch
- neutralize a sampled white object
- click neutral color for white balance
- remove color cast from a known neutral
- balance RGB from a frame sample
- use gray card to correct a clip
- eyedropper white balance without GUI
- sample neutral patch and set gain
- equalize red green blue channels
- automatic neutral-patch correction
- white balance one clip at a timecode
- correct cast from exported Color frame

## What it does

Balance clip color from a sampled neutral patch.

## Do not use when

Use `color page qualifier-sample` when the user only wants RGB/HSV/HSL/scope measurements or is not yet certain the patch is neutral; it exports/samples without writing gains. Use `color page shot-match-analyze`/`shot-match-apply` when balancing one shot to a separate reference frame rather than forcing one patch to gray. Use `color page primary-set --temperature/--tint` or `primary-gui-set` when the requested correction is expressed in Color-page temperature/tint controls and should preserve existing Gain RGB. Use `color page wheel-set` for already-known explicit gains. Do not use this command on skin, colored fabric, saturated highlights, clipped whites, black/shadow patches, mixed-light boundaries, subtitles or any object whose neutral reflectance is not known—the algorithm will faithfully remove the object's real color.

## Preflight and readback

Run `color page qualifier-sample` at the same coordinates/radius, inspect the saved PNG, and confirm the patch is neutral, unclipped, well exposed and free of edges/overlays.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; current clip at sample position when omitted
- `--x` (required) — Normalized neutral sample X coordinate across the Color Page frame (0..1)
- `--y` (required) — Normalized neutral sample Y coordinate down the Color Page frame (0..1)
- `--radius` (optional, default: `8`) — Pixel radius around the neutral sample point (0..200)
- `--at` (optional) — Optional timeline position to sample before restoring the playhead
- `--strength` (optional, default: `1.0`) — Blend strength for computed RGB gain correction (0..1)
- `--output/-o` (optional, default: `"color_white_balance_sample.png"`) — Exported frame path used for white balance sampling

## Boundaries and gotchas

- `--strength 0` is destructive, not a no-op.
- `--at` controls the sampled timeline frame; without `--at`, the current playhead is sampled.
- It does not account for color space, camera metadata, scene-linear exposure, illuminant models or perceptual neutrality.
- The command exports before mutation only.
- There is no `--node` option.
- Clip names have no track/index disambiguator, so duplicate names remain ambiguous.
- Sampling a transition/composite at `--at` may also include pixels not belonging solely to the target clip.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page white-balance-picker --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
