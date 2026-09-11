# `video generate`

Syntax: `cutagent video generate --prompt VALUE [--resolution VALUE] [--ratio VALUE] [--duration VALUE] [--seed VALUE]`

## Search terms

- video generate
- Generate a video and return its downloaded file and artifact in the active chat.
- video generate help
- video generate command

## What it does

Generate a video and return its downloaded file and artifact in the active chat.

## Do not use when

Do not use for editing existing footage or unless the user has requested AI-generated video. Do not request account tokens or provider keys. Do not retry a pending generation with changed settings merely because the request is taking time.

## Preflight and readback

Choose the description, resolution, aspect ratio, duration, and optional seed. Run from a signed-in CutAgent chat so the downloaded artifact belongs to that chat. After success, use output_path to import or append the file with CutAgent CLI if requested. Inspect the resulting DaVinci Resolve state after placement.

## Public arguments and options

- `--prompt` (required) — Describe the video to generate
- `--resolution` (optional, default: `"720P"`) — 720P or 1080P
- `--ratio` (optional, default: `"16:9"`) — Video aspect ratio
- `--duration` (optional, default: `5`) — Duration in seconds
- `--seed` (optional) — Optional generation seed

## Boundaries and gotchas

- It does not guarantee identical output.
- A local DaVinci Resolve installation alone does not provide this generation service.

## Examples

- `cutagent video generate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
