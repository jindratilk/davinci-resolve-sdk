# `color page resolvefx-param-set`

Syntax: `cutagent color page resolvefx-param-set [CLIP_NAME] [--node-index VALUE] --param VALUE --value VALUE [--type VALUE] [--fx VALUE] [--require-render-proof]`

## Search terms

- set ResolveFX parameter
- change Box Blur strength
- set plugin parameter by ID
- configure ResolveFX bool int double string
- tune Color page effect with render proof
- edit HStrength on Box Blur

## What it does

Set a DaVinci Resolve effects OFX option on a clip Color Page node.

## Do not use when

Use `resolvefx-add` first when no ResolveFX exists on that node; this command cannot create the tool block. Use a dedicated high-level command when available because arbitrary raw parameter IDs are not artist-safe. Do not use `--setup-only` for final acceptance. Do not use this to swap effect type—`--fx` only guards; `resolvefx-add` replaces the effect.

## Preflight and readback

Inspect render-diff metrics and the actual effect result for direction/magnitude/artifacts.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--node-index/--node` (optional, default: `1`) — 1-based Color Page node index containing the ResolveFX OFX tool
- `--param` (required) — ResolveFX OFX option name; Box Blur accepts 'strength' alias for HStrength
- `--value` (required) — Parameter value
- `--type` (optional, default: `"double"`) — Value type: auto, double, int, bool, or string
- `--fx` (optional) — Optional current ResolveFX name/plugin id guard
- `--require-render-proof/--setup-only` (optional, default: `true`) — Export before/after Color Page frames and fail unless rendered pixels change

## Boundaries and gotchas

- Dry-run validates almost nothing beyond node sign.
- The default type is `double`; it is not inferred unless `--type auto` is requested.
- Bool parsing treats only `1/true/yes/on` as true; every other string—including a typo—is encoded false without a vocabulary error.
- Double encoding does not finite-check values.
- `--setup-only` intentionally returns partial/readback-only even when bytes match.
- It must not be described as visually applied.

## Examples

- `cutagent color page resolvefx-param-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
