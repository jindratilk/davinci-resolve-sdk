# `color page ofx-glow-set`

Syntax: `cutagent color page ofx-glow-set [CLIP_NAME] [--gain VALUE]`

## Search terms

- add glow to clip
- soft glow effect
- make highlights bloom
- dreamy glow
- finishing glow
- soften bright highlights
- neon bloom
- add SoftGlow
- luminous halo effect
- Color page glow

## What it does

Apply a supported Color Page finishing glow through the Fusion SoftGlow.

## Do not use when

Use `fusion comp tool-add --type SoftGlow` (and Fusion input setters) for explicit control over comp/tool naming and additional SoftGlow inputs. Use `softening-set` for Blur rather than highlight bloom, and `sharpen-set` for UnsharpMask.

## Preflight and readback

Before running, inspect Fusion comp count and comp 1's main chain, record existing SoftGlow names and render a reference frame. Confirm that inserting after the current main-output source is the intended effect order. If a later semantic check fails, remove the newly named tool or restore the comp from a saved setting/version.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--gain` (optional, default: `0.35`) — SoftGlow Gain value, 0..5

## Boundaries and gotchas

- `--gain 0` is allowed and still inserts a SoftGlow tool, potentially adding graph complexity with little/no visible result.
- The accepted range is 0 through 5 inclusive.
- Prefer an exact name where duplicate media names/context are possible.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page ofx-glow-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
