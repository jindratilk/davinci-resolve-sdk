# `color page sharpen-set`

Syntax: `cutagent color page sharpen-set [CLIP_NAME] [--amount VALUE]`

## Search terms

- sharpen a clip
- add finishing sharpness
- unsharp mask video
- make footage crisper
- enhance edge detail
- add Fusion UnsharpMask
- sharpen selected timeline clip
- apply mild output sharpening
- increase perceived detail
- clip-level Fusion sharpen workaround

## What it does

Apply a supported Color Page finishing sharpen through the Fusion UnsharpMask.

## Do not use when

Use `fusion effect sharpen` when the user is explicitly working inside the currently active Fusion composition and accepts that command's looser, active-comp targeting.

## Preflight and readback

Before running, resolve duplicate clip names, inspect Fusion comp 1 with `clip fusion tools`, and decide whether an existing UnsharpMask should be adjusted rather than duplicated. Record the current main chain and export a reference frame if subjective edge quality or halos matter. Export/compare a detailed frame at full resolution; the built-in verification proves graph membership/type, not visible sharpening or the actual parameter readback.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--amount` (optional, default: `0.35`) — UnsharpMask Amount value, 0..5

## Boundaries and gotchas

- If a later step fails, graph restoration can remove the added tool but does not explicitly remove the newly created empty composition.
- The accepted Amount range is 0..5 inclusive.
- Omit the name only when the clip under the current playhead is definitely intended.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page sharpen-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
