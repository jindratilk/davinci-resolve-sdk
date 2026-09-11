# `fusion comp play`

Syntax: `cutagent fusion comp play`

## Search terms

- play Fusion composition
- preview Fusion animation
- start comp playback
- run Fusion timeline
- preview node graph motion
- play current Fusion comp
- start Fusion viewer playback
- audition Fusion animation
- check animated Fusion graphic
- loop composition preview
- advance Fusion CurrentTime
- preview render range in Fusion

## What it does

Play the composition.

## Do not use when

`fusion comp play` previews only the implicit active Fusion composition context.
Playback and render/cache operations have different completion semantics.
Use `fusion comp range START END` before play when a specific local preview range is required. Play provides no range arguments.
Use `clip fusion list`, page/playhead positioning, or an explicit clip-scoped command when the target comp is ambiguous. Play cannot choose among multiple comps on a clip.
Do not use `--dry-run` as a safety preview. It performs the mutation.

## Preflight and readback

Before play, identify the exact project, timeline, clip, and composition. Put the playhead inside the intended clip or explicitly open the desired comp on the Fusion page, then run `fusion comp current` and verify the comp name plus render/global range.
Stop any existing timeline or comp playback first when the current playback state is uncertain. Check whether expensive nodes, missing media, third-party plugins, high-resolution settings, or uncached effects make interactive playback risky or misleading.
Always pair bounded automated tests with `fusion comp stop`, including error/cleanup paths.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- The command does not report or enforce loop mode, playback direction, proxy quality, viewer selection, real-time status, cache completion, or audio behavior.
- Automations must include cleanup.
- Starting playback can trigger expensive graph evaluation, GPU/VRAM use, cache activity, plugin execution, and media I/O even though it does not rewrite graph nodes.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion comp play --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
