# `codec build`

Syntax: `cutagent codec build PATH`

## Search terms

- build codec plugin
- compile DaVinci Resolve IOPlugin
- run make for encoder plugin
- compile CodecPlugin SDK sample
- diagnose codec make failure
- build custom render codec

## What it does

Build a codec add-on project.

## Do not use when

Use `codec scaffold` only to create the two-file placeholder, `codec sample copy` to obtain a real SDK example, `codec package` after build outputs are ready, and `codec install` only for the finished plugin bundle. Do not use this command to build normal render jobs or transcode media; those belong to `render` or `media transcode` commands.

## Preflight and readback

A successful make return code still does not prove DaVinci Resolve can discover or encode with the plugin; package/install it and restart DaVinci Resolve when the SDK requires that, then perform a real render smoke.

## Public arguments and options

- `PATH` (required) — Project folder

## Examples

- `cutagent codec build --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
