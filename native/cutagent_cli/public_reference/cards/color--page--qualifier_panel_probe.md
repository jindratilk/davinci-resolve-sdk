# `color page qualifier-panel-probe`

Syntax: `cutagent color page qualifier-panel-probe [CLIP_NAME]`

## Search terms

- inspect Qualifier panel controls
- check HSL qualifier GUI support
- discover settable matte controls
- see whether qualifier automation is safe
- list visible qualifier fields
- diagnose qualifier GUI route
- verify Color page Qualifier palette readiness
- find Clean Black Clean White Blur controls

## What it does

Inspect Color Page Qualifier panel controls through the custom edit-owned interface.

## Preflight and readback

Before probing, make the intended clip and Color node current, keep DaVinci Resolve visible, and ensure macOS Accessibility and Screen Recording permission. Record the original playhead if a named clip is supplied and downstream workflow needs it restored. Visually verify that the captured rectangle actually contains the intended Qualifier palette and restore page/playhead manually if needed.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip

## Boundaries and gotchas

- Matte support can be true from any matte-labelled settable control or inferred Clean Black/Clean White/Blur field; it does not promise that Denoise, Grow/Shrink, or every requested refinement is exposed.
- A whitespace-only clip is rejected with the misleading message `Color Page Power Window tracking clip name must not be empty`; that wording comes from the shared normalizer and does not mean this command tracks a window.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page qualifier-panel-probe --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
