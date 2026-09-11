# `media selected list`

Syntax: `cutagent media selected list`

## Search terms

- list selected Media Pool clips
- get current bin selection
- inspect selected source assets
- see GUI Media Pool selection
- verify selected clip
- find selected timeline entry
- check what media is highlighted

## What it does

List selected media pool clips.

## Do not use when

Do not use this to find selected timeline clips on the Edit page; this is Media Pool/bin selection. Do not use response `index` as a persistent Media Pool item ID—it is only enumeration order. Use search/info when no selection exists or a deterministic asset target is required.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Selecting one does not necessarily make it the active project timeline.
- Rows omit folder path and media ID, so duplicate selected names may remain ambiguous.

## Examples

- `cutagent media selected list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
