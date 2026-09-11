# `audio voice-list`

Syntax: `cutagent audio voice-list [--source VALUE] [--search VALUE] [--page-token VALUE] [--page VALUE] [--limit VALUE] [--language VALUE] [--accent VALUE] [--gender VALUE] [--age VALUE] [--use-case VALUE] [--sort VALUE] [--include-custom-rates]`

## Search terms

- list ElevenLabs voices
- choose AI voice
- find voiceover voice
- browse narration voices
- voice id for text to speech
- search ElevenLabs catalog
- CutAgent voice generation

## What it does

List saved and default voices and search the public ElevenLabs Voice Library.

## Do not use when

Do not ask the user for provider credentials or invent a voice id. Starter accounts are not entitled to this feature; it requires legacy Hobby/current Creator or higher.

## Preflight and readback

Confirm the CutAgent desktop app is open and signed in. Search `--source account` first, then use `--source library` with language, accent, use-case, and popularity filters when the account collection has no suitable voice. Present at most three useful matches when voice choice is subjective. If the catalog is empty, retry with a less restrictive search before concluding that no voices are available.

## Public arguments and options

- `--source` (optional, default: `"account"`) — Voice source: account or library
- `--search` (optional) — Filter ElevenLabs voices by name, description, or label
- `--page-token` (optional) — Continue from next_page_token returned by a previous voice list
- `--page` (optional) — Zero-based public Voice Library page
- `--limit` (optional, default: `50`) — Maximum voices to return
- `--language` (optional) — Voice Library language code, such as en or cs
- `--accent` (optional) — Voice Library accent filter
- `--gender` (optional) — Voice Library gender filter
- `--age` (optional) — Voice Library age filter
- `--use-case` (optional) — Voice Library use case filter
- `--sort` (optional) — Voice Library sort: trending, usage_character_count_1y, cloned_by_count, or created_date
- `--include-custom-rates` (optional, default: `false`) — Include voices with a provider credit multiplier above 1x

## Boundaries and gotchas

- A Hobby-equivalent plan or higher is required; the current public equivalent of legacy Hobby is Creator.
- `--search` is optional and searches provider-managed voice metadata; results may change as the provider catalog changes.
- `--limit` accepts 1 through 100 and defaults to 50.
- `--include-custom-rates` must be an intentional cost-aware choice.
- The one-time broker grant is bound to the exact authorized arguments and cannot be reused.

## Examples

- `cutagent audio voice-list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
