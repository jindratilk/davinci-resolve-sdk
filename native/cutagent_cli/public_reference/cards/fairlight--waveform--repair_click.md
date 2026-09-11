# `fairlight waveform repair-click`

Syntax: `cutagent fairlight waveform repair-click [--clip VALUE] [--at VALUE]`

## Search terms

- repair audio click
- remove click from waveform
- fix pop in dialogue
- Fairlight sample repair
- declick one audio sample
- heal waveform spike
- repair mouth click
- remove digital pop
- fix crackle at timeline position
- edit audio samples directly
- redraw bad waveform sample
- repair click at timecode

## What it does

Check Fairlight waveform and sample repair availability.

## Do not use when

It cannot diagnose or verify an audible click.
Use fades or `fairlight transition add` when the click is caused by an edit discontinuity at a clip boundary and a short fade/crossfade is the intended non-destructive fix.
Do not claim that as sample repair.
Use gain/keyframe/automation controls only when intentionally attenuating a short region is acceptable. Lowering a region is different from reconstructing damaged samples and may affect desired speech/music.
Manual export/process/reimport may be required.
Do not interpret clip name or `--at` acceptance as target validation. This command stops before either selector is resolved.

## Preflight and readback

Before calling, decide whether the artifact is at an edit boundary or embedded inside a clip. Inspect the clip identity, exact record/source position, neighboring handles, and listen at high zoom. If a fade/crossfade can solve a boundary click without destructive sample work, use that supported route instead.
Branch immediately to a human DaVinci Resolve sample-editor workflow or external audio repair workflow; do not retry with different spellings.
For manual/external repair, preserve the original media, work on a duplicate/version, record sample rate/channel layout/time alignment, and render/audition before and after at the same gain. Confirm sync, source duration, handles, channel mapping, and that only the intended transient changed.
There is no CutAgent “after” readback for this command because no mutation occurs. `fairlight waveform info` is not post-repair proof; use the repaired audio waveform/listening/render/file comparison instead.

## Public arguments and options

- `--clip` (optional) — Timeline clip name or item id
- `--at` (optional) — Timeline/sample position to repair

## Boundaries and gotchas

- Both `--clip` and `--at` are optional.
- Manual UI availability does not change this command's `unsupported` contract.
- Reimport/round-trip verification must cover sync and format, not only perceived click removal.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight waveform repair-click --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
