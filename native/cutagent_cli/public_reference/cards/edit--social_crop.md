# `edit social-crop`

Syntax: `cutagent edit social-crop [CLIP_NAME] [--format VALUE] [--source-aspect VALUE] [--pan VALUE] [--tilt VALUE] [--zoom VALUE] [--all-clips] [--set-timeline]`

## Search terms

- crop video for TikTok
- make vertical 9:16 timeline
- reframe landscape for Reels
- convert video to YouTube Shorts format
- make square social edit
- crop 16:9 to portrait 4:5
- zoom and pan for vertical video
- apply social format to all clips
- set Instagram post resolution
- center crop horizontal footage vertically
- reframe current clip for mobile
- change timeline to 1080x1920

## What it does

Apply a social crop and reframe.

## Do not use when

Use `edit camera-pip` for a small inset over a background, `clip transform` for explicit general transforms/crops without changing timeline resolution, or dynamic/keyframed/Fusion tracking tools when the subject moves. Use project/timeline settings commands when only output resolution should change and existing per-clip reframes must remain untouched.
Do not use this as “smart reframe”: pan/tilt are fixed values supplied by the agent, and source aspect is trusted input rather than inspected media metadata. Do not use `--all-clips` on a mixed-aspect/individually framed timeline unless overwriting every static transform is intentional. Use `--no-set-timeline` when the active sequence resolution must not change.

## Preflight and readback

Before mutation, record current timeline resolution/custom-settings state and every target's transform/keyframes. Inspect actual source aspect, input scaling, pixel aspect, rotation and subject position for each clip. Choose an explicit format, source aspect, pan/tilt and whether the global timeline resolution change is desired; checkpoint the timeline.
Afterward, independently reread timeline width/height and every target transform, then render representative frames for fill, subject framing, cutoff, letterboxing and mixed-source behavior. Verify non-target clips if resolution changed, because the global canvas affects the entire sequence. Treat returned applied properties as requests unless external readback/pixels confirm them.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name (defaults to current timeline item)
- `--format` (optional, default: `"9:16"`) — Social format: 9:16|1:1|4:5|16:9|vertical|square|portrait
- `--source-aspect` (optional, default: `"16:9"`) — Source aspect ratio, e.g. 16:9 or 4:3
- `--pan/--position-x` (optional, default: `0.0`) — DaVinci Resolve Pan value for horizontal reframing
- `--tilt/--position-y` (optional, default: `0.0`) — DaVinci Resolve Tilt value for vertical reframing
- `--zoom` (optional) — Override computed fill zoom
- `--all-clips` (optional, default: `false`) — Apply to all video timeline items
- `--set-timeline/--no-set-timeline` (optional, default: `true`) — Set active timeline resolution to the selected social format

## Boundaries and gotchas

- `--set-timeline` is on by default.
- A missing named clip or empty `--all-clips` scope can fail after resolution settings already changed.
- Fixed aliases are case-insensitive but there is no arbitrary output-size option.
- `--source-aspect` accepts preset aliases, `WIDTH:HEIGHT` or a positive numeric ratio.
- Default source aspect is always 16:9, including when `--all-clips` contains square, vertical, anamorphic, rotated or still media.
- `--zoom` bypasses aspect math completely and only checks `>0`; no upper bound or fit validation exists.
- It does not set CropLeft/Right/Top/Bottom.
- Duplicate names can silently target the first video-track traversal match.
- `--all-clips` ignores any positional clip argument and enumerates every readable video item across all video tracks.
- When timeline setting is enabled, overall verification is based on resolution readback only.
- The command does not save the project, add an undo checkpoint, restore prior settings/transforms or perform face/subject tracking.

## Examples

- `cutagent edit social-crop --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
