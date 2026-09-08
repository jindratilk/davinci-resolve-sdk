"""Audio analysis, preprocessing, and hosted voiceover commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from ..core import audio_ops
from ..core import hosted_voiceover
from ..errors import handle_errors, ValidationError
from ..output import (
    output,
    is_dry_run,
    dry_run_message,
    set_capability_context,
    set_execution_engine,
    set_recoverability,
    set_verification_status,
)
from ..policy import enforce_mutation_policy
from ..connection import get_connection
from ..core import media_pool as media_pool_ops
from ..core import timeline_ops

app = typer.Typer(
    no_args_is_help=True,
    help="File-level audio helpers and hosted voiceover generation. Use `clip audio-*` or `fairlight *` for DaVinci Resolve native audio work.",
)


def _pronunciation_dictionary_locators(values: Optional[list[str]]) -> list[dict[str, str]] | None:
    if not values:
        return None
    if len(values) > 3:
        raise ValidationError("--pronunciation-dictionary may be repeated at most 3 times.")
    locators: list[dict[str, str]] = []
    for raw_value in values:
        dictionary_id, separator, version_id = raw_value.strip().partition(":")
        if not dictionary_id or (separator and not version_id):
            raise ValidationError("--pronunciation-dictionary must be DICTIONARY_ID or DICTIONARY_ID:VERSION_ID.")
        locators.append({
            "pronunciation_dictionary_id": dictionary_id,
            **({"version_id": version_id} if version_id else {}),
        })
    return locators


@app.command("voice-list")
@handle_errors
def voice_list(
    source: str = typer.Option("account", "--source", help="Voice source: account or library"),
    search: Optional[str] = typer.Option(None, "--search", help="Filter ElevenLabs voices by name, description, or label"),
    page_token: Optional[str] = typer.Option(None, "--page-token", help="Continue from next_page_token returned by a previous voice list"),
    page: Optional[int] = typer.Option(None, "--page", min=0, max=10_000, help="Zero-based public Voice Library page"),
    limit: int = typer.Option(50, "--limit", min=1, max=100, help="Maximum voices to return"),
    language: Optional[str] = typer.Option(None, "--language", help="Voice Library language code, such as en or cs"),
    accent: Optional[str] = typer.Option(None, "--accent", help="Voice Library accent filter"),
    gender: Optional[str] = typer.Option(None, "--gender", help="Voice Library gender filter"),
    age: Optional[str] = typer.Option(None, "--age", help="Voice Library age filter"),
    use_case: Optional[str] = typer.Option(None, "--use-case", help="Voice Library use case filter"),
    sort: Optional[str] = typer.Option(None, "--sort", help="Voice Library sort: trending, usage_character_count_1y, cloned_by_count, or created_date"),
    include_custom_rates: bool = typer.Option(False, "--include-custom-rates", help="Include voices with a provider credit multiplier above 1x"),
):
    """List saved/default voices or search the public ElevenLabs Voice Library."""
    normalized_source = source.strip().lower()
    if normalized_source not in {"account", "library"}:
        raise ValidationError("--source must be account or library.")
    if sort and sort.strip() not in {"trending", "usage_character_count_1y", "cloned_by_count", "created_date"}:
        raise ValidationError("--sort must be trending, usage_character_count_1y, cloned_by_count, or created_date.")
    if normalized_source == "account" and any((page is not None, language, accent, gender, age, use_case, sort)):
        raise ValidationError("--page, --language, --accent, --gender, --age, --use-case, and --sort require --source library.")
    if normalized_source == "library" and page_token:
        raise ValidationError("--page-token applies only to --source account; use --page for the Voice Library.")
    set_capability_context("audio.voiceover", "supported")
    set_execution_engine("hosted_api")
    enforce_mutation_policy("audio.voiceover", intended_engine="hosted_api", mutating=False)
    if is_dry_run():
        dry_run_message(f"Would list ElevenLabs voices from the {normalized_source} catalog.")
        return
    result = hosted_voiceover.broker_request({
        "operation": "list",
        "source": normalized_source,
        "search": search.strip() if isinstance(search, str) and search.strip() else None,
        "page_token": page_token.strip() if isinstance(page_token, str) and page_token.strip() else None,
        "page": page,
        "limit": limit,
        "language": language.strip() if isinstance(language, str) and language.strip() else None,
        "accent": accent.strip() if isinstance(accent, str) and accent.strip() else None,
        "gender": gender.strip() if isinstance(gender, str) and gender.strip() else None,
        "age": age.strip() if isinstance(age, str) and age.strip() else None,
        "use_case": use_case.strip() if isinstance(use_case, str) and use_case.strip() else None,
        "sort": sort.strip() if isinstance(sort, str) and sort.strip() else None,
        "include_custom_rates": include_custom_rates,
    })
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(result, title="ElevenLabs Voices")


@app.command("voice-generate")
@handle_errors
def voice_generate(
    voice_id: str = typer.Option(
        ...,
        "--voice-id",
        help="ElevenLabs voice id from audio voice-list or the public Voice Library",
    ),
    text: str = typer.Option(..., "--text", help="Exact text to synthesize (1-10000 characters)"),
    output_file: str = typer.Option(..., "--output", "-o", help="Destination MP3 path"),
    stability: Optional[float] = typer.Option(None, "--stability", min=0.0, max=1.0, help="Delivery consistency from 0 to 1"),
    similarity_boost: Optional[float] = typer.Option(None, "--similarity-boost", min=0.0, max=1.0, help="Similarity to the source voice from 0 to 1"),
    style: Optional[float] = typer.Option(None, "--style", min=0.0, max=1.0, help="Style exaggeration from 0 to 1"),
    speaker_boost: Optional[bool] = typer.Option(None, "--speaker-boost/--no-speaker-boost", help="Override speaker similarity boost"),
    speed: Optional[float] = typer.Option(None, "--speed", min=0.7, max=1.2, help="Speaking speed from 0.7 to 1.2"),
    seed: Optional[int] = typer.Option(None, "--seed", min=0, max=4_294_967_295, help="Best-effort deterministic sampling seed"),
    pronunciation_dictionary: Optional[list[str]] = typer.Option(
        None,
        "--pronunciation-dictionary",
        help="Pronunciation dictionary as DICTIONARY_ID[:VERSION_ID]; repeat up to 3 times",
    ),
    previous_text: Optional[str] = typer.Option(None, "--previous-text", help="Text before this segment for continuity"),
    next_text: Optional[str] = typer.Option(None, "--next-text", help="Text after this segment for continuity"),
    previous_request_id: Optional[list[str]] = typer.Option(
        None, "--previous-request-id", help="Previous ElevenLabs request id; repeat up to 3 times",
    ),
    next_request_id: Optional[list[str]] = typer.Option(
        None, "--next-request-id", help="Following ElevenLabs request id; repeat up to 3 times",
    ),
    apply_text_normalization: Optional[str] = typer.Option(
        None, "--text-normalize", help="Text processing mode: auto, on, or off",
    ),
    apply_language_text_normalization: Optional[bool] = typer.Option(
        None,
        "--language-text-normalize/--no-language-text-normalize",
        help="Toggle language-specific text processing; currently useful for Japanese and may add latency",
    ),
    force: bool = typer.Option(False, "--force", help="Replace an existing output file"),
):
    """Generate and download an ElevenLabs voiceover through CutAgent usage."""
    normalized_voice_id = voice_id.strip()
    normalized_text = text.strip()
    if not normalized_voice_id or len(normalized_voice_id) < 8:
        raise ValidationError("--voice-id must be a valid ElevenLabs voice id.")
    character_count = len(normalized_text)
    if not normalized_text or character_count > 10_000:
        raise ValidationError("--text must contain between 1 and 10000 characters.")
    if apply_text_normalization is not None and apply_text_normalization not in {"auto", "on", "off"}:
        raise ValidationError("--text-normalize must be auto, on, or off.")
    if previous_text is not None and (not previous_text.strip() or len(previous_text.strip()) > 10_000):
        raise ValidationError("--previous-text must contain between 1 and 10000 characters.")
    if next_text is not None and (not next_text.strip() or len(next_text.strip()) > 10_000):
        raise ValidationError("--next-text must contain between 1 and 10000 characters.")
    if previous_request_id is not None and len(previous_request_id) > 3:
        raise ValidationError("--previous-request-id may be repeated at most 3 times.")
    if next_request_id is not None and len(next_request_id) > 3:
        raise ValidationError("--next-request-id may be repeated at most 3 times.")
    dictionary_locators = _pronunciation_dictionary_locators(pronunciation_dictionary)
    destination = Path(output_file).expanduser().resolve(strict=False)
    voice_settings = {
        key: value
        for key, value in {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "use_speaker_boost": speaker_boost,
            "speed": speed,
        }.items()
        if value is not None
    } or None
    set_capability_context("audio.voiceover", "supported")
    set_execution_engine("hosted_api")
    enforce_mutation_policy("audio.voiceover", intended_engine="hosted_api", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(
            f"Would generate {character_count} characters with ElevenLabs voice {normalized_voice_id} and write {destination}."
        )
        return
    destination, reservation = hosted_voiceover.prepare_output_path(output_file, force=force)
    try:
        result = hosted_voiceover.broker_request({
            "operation": "generate",
            "voice_id": normalized_voice_id,
            "text": normalized_text,
            "voice_settings": voice_settings,
            "seed": seed,
            "pronunciation_dictionary_locators": dictionary_locators,
            "previous_text": previous_text.strip() if previous_text is not None else None,
            "next_text": next_text.strip() if next_text is not None else None,
            "previous_request_ids": previous_request_id or None,
            "next_request_ids": next_request_id or None,
            "apply_text_normalization": apply_text_normalization,
            "apply_language_text_normalization": apply_language_text_normalization,
        })
        size_bytes = hosted_voiceover.download_audio(result.get("audio_url"), destination, reservation)
        reservation = None
    except Exception:
        hosted_voiceover.cleanup_reservation(destination, reservation)
        raise
    set_verification_status("file_verified")
    set_recoverability("not_applicable")
    output({
        "output_path": str(destination),
        "provider": result.get("provider", "elevenlabs"),
        "model": result.get("model"),
        "voice_id": result.get("voice_id", normalized_voice_id),
        "voice_settings": result.get("voice_settings", voice_settings),
        "rate_multiplier": result.get("rate_multiplier", 1),
        "seed": result.get("seed", seed),
        "character_count": result.get("character_count", character_count),
        "size_bytes": size_bytes,
        "usage": result.get("usage"),
        "provider_request_id": result.get("provider_request_id"),
        "next_step": "Use this output_path with media import or media append to place the voiceover in DaVinci Resolve.",
    }, title="ElevenLabs Voiceover")


@app.command("voice-place")
@handle_errors
def voice_place(
    path: str = typer.Argument(..., help="Retained generated-voice MP3 path"),
    track_index: int = typer.Option(..., "--track", min=1, help="One-based target audio track"),
    absolute_record_frame: int = typer.Option(..., "--absolute-record-frame", min=0, help="Exact DaVinci Resolve API recordFrame"),
):
    """Import one generated voice asset and place that exact Media Pool item."""
    source = Path(path).expanduser().resolve(strict=False)
    if not source.is_file():
        raise ValidationError("Generated voice asset was not found.", details={"path": str(source)})
    if source.suffix.lower() != ".mp3":
        raise ValidationError("Generated voice placement requires an MP3 asset.", details={"path": str(source)})
    set_capability_context("audio.voiceover", "supported")
    set_execution_engine("api_native")
    enforce_mutation_policy("audio.voice_place", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(
            f"Would import the retained generated voice asset and place it on audio track {track_index} "
            f"at absolute record frame {absolute_record_frame}."
        )
        return

    conn = get_connection(require_timeline=True)
    timeline_ops.require_sdk_marker_mutation_guard(conn)
    importer = getattr(conn.media_pool, "ImportMedia", None)
    if not callable(importer):
        raise ValidationError("MediaPool.ImportMedia is unavailable for generated voice placement.")
    imported = importer([str(source)])
    if not isinstance(imported, list) or len(imported) != 1:
        raise ValidationError(
            "Generated voice import did not return exactly one Media Pool item.",
            details={"imported_count": len(imported) if isinstance(imported, list) else None},
        )
    media_item = imported[0]
    item_name = media_item.GetName() if hasattr(media_item, "GetName") else source.name
    details = media_pool_ops.append_resolved_clip_to_timeline(
        conn,
        media_item,
        name=str(item_name or source.name),
        track_type="audio",
        track_index=track_index,
        absolute_record_frame=absolute_record_frame,
        return_details=True,
    )
    media_id = media_item.GetUniqueId() if hasattr(media_item, "GetUniqueId") else None
    # The bridge performs the authoritative before/after timeline readback for
    # SDK placement. Here we can only prove that DaVinci Resolve returned one
    # appended item for the exact Media Pool object supplied above.
    set_verification_status("partial")
    set_recoverability("manual")
    output({
        "action": "audio.voice_place",
        "changed": True,
        "media_pool_item_id": str(media_id) if media_id not in (None, "") else None,
        "track_index": details.get("track_index"),
        "record_frame": details.get("record_frame"),
        "append_result_count": details.get("append_result_count"),
        "timeline_items": details.get("timeline_items"),
    }, title="Generated Voice Placement")


def _check_input(path: str) -> None:
    input_path = Path(path)
    if not input_path.exists():
        raise ValidationError(
            f"Input file not found: {path}",
            details={
                "path": path,
                "hint": "audio.* commands preprocess source media files. For DaVinci Resolve native routes use clip audio-eq, fairlight eq set, fairlight dynamics, or fairlight ai dialogue-leveler.",
            },
        )
    if not input_path.is_file():
        raise ValidationError(
            f"Input path is not a file: {path}",
            details={
                "path": path,
                "path_type": "directory" if input_path.is_dir() else "not_file",
                "hint": "Pass a media file path, not a directory.",
            },
        )


@app.command()
@handle_errors
def reverb(
    input: str = typer.Argument(..., help="Input media file"),
    output_file: Optional[str] = typer.Option(None, "--output", "-o", help="Output file"),
):
    _check_input(input)
    audio_stream_count = audio_ops.audio_stream_count(input)
    if audio_stream_count < 1:
        raise ValidationError(
            "No audio streams found",
            details={"audio_stream_count": 0, "streams": []},
        )
    out = output_file or audio_ops.default_output(input)
    audio_ops.validate_output_file_path(out)
    enforce_mutation_policy(
        None,
        intended_engine="workaround_setting",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(f"Would apply reverb to '{input}' and write '{out}'")
        return
    out = audio_ops.reverb(input, out, validate_audio_streams=False)
    set_verification_status("file_verified")
    set_recoverability("not_applicable")
    output({"operation": "reverb", "input": input, "output": out, "audio_stream_count": audio_stream_count})


@app.command()
@handle_errors
def info(
    input: str = typer.Argument(..., help="Input media file"),
):
    _check_input(input)
    data = audio_ops.info(input)
    if "error" in data:
        raise ValidationError(
            data["error"],
            details={key: value for key, value in data.items() if key != "error"},
        )
    output(data, title="Audio Info")


@app.command()
@handle_errors
def duck(
    input_media: str = typer.Argument(..., help="Input media file"),
    speech_track: int = typer.Option(..., "--speech-track", min=1, help="Speech/dialogue audio track index (1-based)"),
    music_track: int = typer.Option(..., "--music-track", min=1, help="Music bed audio track index (1-based)"),
    threshold_db: float = typer.Option(-20.0, "--threshold-db", help="Sidechain threshold in dB"),
    ratio: float = typer.Option(8.0, "--ratio", help="Compression ratio"),
    attack_ms: float = typer.Option(20.0, "--attack-ms", help="Attack time in milliseconds"),
    release_ms: float = typer.Option(300.0, "--release-ms", help="Release time in milliseconds"),
    output_file: Optional[str] = typer.Option(None, "--output", "-o", help="Output media path"),
    replace_media: Optional[str] = typer.Option(None, "--replace-media", help="Relink Media Pool clip name to ducked output"),
):
    """Apply sidechain ducking using ffmpeg pipeline with optional media relink."""
    audio_ops.validate_duck_parameters(
        speech_track=speech_track,
        music_track=music_track,
        threshold_db=threshold_db,
        ratio=ratio,
        attack_ms=attack_ms,
        release_ms=release_ms,
    )
    _check_input(input_media)
    audio_ops.validate_duck_streams(input_media, speech_track=speech_track, music_track=music_track)
    enforce_mutation_policy(
        "edit.audio_duck_sidechain",
        intended_engine="workaround_setting",
        mutating=not is_dry_run(),
    )

    if is_dry_run():
        dry_run_message(
            f"Would duck '{input_media}' (speech_track={speech_track}, music_track={music_track})"
            + (f" and relink '{replace_media}'" if replace_media else "")
        )
        return

    out = audio_ops.duck(
        input_media,
        speech_track=speech_track,
        music_track=music_track,
        threshold_db=threshold_db,
        ratio=ratio,
        attack_ms=attack_ms,
        release_ms=release_ms,
        output=output_file,
        validate_stream_indexes=False,
    )

    relink = None
    if replace_media:
        conn = get_connection(require_project=True)
        media_pool_ops.relink_clip(conn, replace_media, out)
        relink = {"clip": replace_media, "path": out}
    else:
        set_verification_status("file_verified")
        set_recoverability("not_applicable")

    output(
        {
            "operation": "duck",
            "input": input_media,
            "output": out,
            "speech_track": speech_track,
            "music_track": music_track,
            "threshold_db": threshold_db,
            "ratio": ratio,
            "attack_ms": attack_ms,
            "release_ms": release_ms,
            "relinked_media": relink,
        },
        title="Audio Duck",
    )


@app.command("waveform-offset")
@handle_errors
def waveform_offset(
    reference: str = typer.Option(..., "--reference", help="Reference media file (offsets are relative to it)"),
    target: str = typer.Option(..., "--target", help="Target media file to align against the reference"),
    fps: float = typer.Option(24.0, "--fps", help="Timeline frame rate used for frame conversion"),
    windows: int = typer.Option(7, "--windows", help="Refinement window count"),
    window_seconds: float = typer.Option(30.0, "--window-seconds", help="Refinement window length in seconds"),
    prior_offset_seconds: Optional[float] = typer.Option(
        None, "--prior-offset-seconds", help="Skip coarse search and refine around this offset"
    ),
    use_metadata: bool = typer.Option(
        True, "--metadata/--no-metadata", help="Read BWF/timecode metadata and report a deterministic prior"
    ),
):
    """Measure the precise audio offset (sub-frame + drift) of target relative to reference."""
    from ..core import sync_metadata, waveform_sync

    _check_input(reference)
    _check_input(target)
    metadata_block = None
    prior = prior_offset_seconds
    if use_metadata:
        reference_metadata = sync_metadata.read_sync_metadata(reference, fps=fps)
        target_metadata = sync_metadata.read_sync_metadata(target, fps=fps)
        metadata_prior = sync_metadata.compute_metadata_prior(reference_metadata, target_metadata)
        metadata_block = {
            "reference": reference_metadata,
            "target": target_metadata,
            "prior_offset_seconds": metadata_prior,
        }
        if prior is None and metadata_prior is not None:
            prior = metadata_prior
    result = waveform_sync.estimate_offset(
        reference,
        target,
        fps,
        windows=windows,
        window_seconds=window_seconds,
        prior_offset_seconds=prior,
    )
    if metadata_block is not None:
        prior_value = metadata_block["prior_offset_seconds"]
        if prior_value is not None and abs(prior_value - result["offset_seconds"]) > 1.0:
            result.setdefault("warnings", []).append("metadata_prior_mismatch")
        result["metadata"] = metadata_block
    set_verification_status("file_verified")
    set_recoverability("not_applicable")
    output(result, title="Waveform Offset")


@app.command("beat-detect")
@handle_errors
def beat_detect(
    input: str = typer.Argument(..., help="Input music or media file"),
    fps: float = typer.Option(24.0, "--fps", help="Timeline frame rate used for frame-snapped beat positions"),
    min_bpm: float = typer.Option(60.0, "--min-bpm", help="Minimum tempo to consider"),
    max_bpm: float = typer.Option(200.0, "--max-bpm", help="Maximum tempo to consider"),
    beats_per_bar: int = typer.Option(4, "--beats-per-bar", min=1, help="Meter used to infer downbeats"),
    bars_per_phrase: int = typer.Option(8, "--bars-per-phrase", min=1, help="Bars used to infer phrase starts"),
    beat_offset: int = typer.Option(0, "--beat-offset", help="Shift the inferred downbeat/phrase grid by this many beats"),
):
    """Detect musical beats and return frame-snapped beat, downbeat, and phrase candidates."""
    from ..core import beat_detection

    _check_input(input)
    enforce_mutation_policy("audio.beat_detection", intended_engine="workaround_setting", mutating=False)
    result = beat_detection.analyze(
        input,
        fps=fps,
        min_bpm=min_bpm,
        max_bpm=max_bpm,
        beats_per_bar=beats_per_bar,
        bars_per_phrase=bars_per_phrase,
        beat_offset=beat_offset,
    )
    set_verification_status("file_verified")
    set_recoverability("not_applicable")
    output(result, title="Beat Detection")


@app.command("probe-subframe")
@handle_errors
def probe_subframe(
    force: bool = typer.Option(False, "--force", help="Re-probe even when a cached verdict exists"),
    rendered_check: bool = typer.Option(
        True, "--render/--no-render", help="Verify rendered audio position, not only clip metadata"
    ),
):
    """Probe whether the connected DaVinci Resolve honors fractional (sub-frame) audio placement."""
    from ..core import subframe_probe

    enforce_mutation_policy(
        "timeline.sync_clips",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would probe DaVinci Resolve sub-frame audio placement on a scratch timeline.")
        return
    conn = get_connection(require_project=True)
    result = subframe_probe.get_subframe_support(conn, force=force, rendered_check=rendered_check)
    set_verification_status("verified" if result.get("verified_render") else "partial")
    output(result, title="Subframe Placement Probe")
