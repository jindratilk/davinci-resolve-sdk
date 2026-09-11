# `color version list`

Syntax: `cutagent color version list [CLIP_NAME]`

## Search terms

- list color versions
- show clip grade versions
- inspect local and remote versions
- find named color version
- enumerate Color page versions
- check alternate grades
- see grading takes for clip
- find duplicate version names
- inspect local remote grade inventory
- what color versions exist
- list saved looks on clip
- check version before load delete

## What it does

List color versions.

## Do not use when

Use `color version activate`/`load` when a named row should become current, `version duplicate`/`add` to create a branch, or `version delete` to remove it.
Use `color inspect`, node inspection, frame export or rendering to compare what the grades actually do; version names are not grade content. Use `color source-grade plan` when deciding whether repeated source instances should use local or remote grading; the presence of a remote name alone does not prove which instances share/load it. Use timeline/clip listing first when a filename occurs multiple times and selecting the first matching occurrence would be unsafe.

## Preflight and readback

Before listing, confirm the current project/timeline. If multiple timeline items share a name, resolve the desired occurrence through surrounding timeline evidence because this command has no track/frame selector.
Afterward, preserve both `name` and `type`, count duplicate rows rather than turning the result into a set, and treat local and remote namespaces independently. Before load/delete, reject ambiguous duplicate names or account for delete's all-matches behavior.

## Public arguments and options

- `CLIP_NAME` (optional)

## Boundaries and gotchas

- Output does not identify the resolved clip at all.
- Exact duplicate names are not collapsed.

## Stable public error codes

- `INVALID_OPTION`

## Examples

- `cutagent color version list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
