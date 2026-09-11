# `timeline dolby analyze`

Syntax: `cutagent timeline dolby analyze [--items VALUE] [--blend-shots] [--enable-project-controls]`

## Search terms

- Dolby Vision timeline analysis
- HDR Dolby project controls
- blend shots analysis
- analyze named timeline clips
- hdrDolbyControlsOn
- hdrMasteringOn
- Dolby analysis diagnostics

## What it does

Run Dolby Vision analysis.

## Do not use when

Do not use this command for a project that is not intentionally configured for Dolby Vision/HDR mastering, or when changing project color-management controls is unacceptable. Use `--no-enable-project-controls` to preserve settings, but configure and verify the required controls manually.
Do not pass uncertain clip names with the default control-enabling behavior.
Inspect the Dolby Vision controls and analyzed shots in DaVinci Resolve.

## Preflight and readback

Before execution, save/checkpoint the project; inspect the active timeline, color science, timeline/output color spaces, working luminance, Dolby version/tuning, and both HDR control settings. Resolve every intended item name and decide whether whole-timeline analysis, named items, or blend-shots behavior is appropriate.
Restore project settings manually from the checkpoint if they changed unintentionally.

## Public arguments and options

- `--items` (optional, repeatable) — Timeline item names
- `--blend-shots` (optional, default: `false`) — Blend shots during analysis
- `--enable-project-controls/--no-enable-project-controls` (optional, default: `true`)

## Boundaries and gotchas

- `--items` is a repeatable option; each occurrence supplies one timeline item name.
- Duplicate names can resolve to the first matching item; this command does not reject ambiguity.
- The no-enable result reports `enabled: false` even if existing settings might already contain the required values, because that branch does not calculate enabled state.
- Timeline summary does not verify Dolby analysis data.
- Dry-run returns only a generic message and ignores item/control/blend details in its data.

## Stable public error codes

- `API_CALL_FAILED`
- `CAPABILITY_NEGOTIATION_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent timeline dolby analyze --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
