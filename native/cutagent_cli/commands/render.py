"""Render / Deliver commands."""

from __future__ import annotations

import json
import os
import hashlib
import subprocess
from pathlib import Path
from typing import Any, Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from ..connection import get_connection
from ..errors import APICallFailed, ValidationError, handle_errors
from ..output import console, dry_run_message, get_output_mode, is_dry_run, mutation_payload, output, set_recoverability, set_verification_status, success
from ..policy import enforce_mutation_policy
from ..external_tools import resolve_tool
from ..core import render_engine, timeline_ops
from ..core._render_engine.presets import save_render_preset
from ..core._render_engine.preset_update import update_render_preset

app = typer.Typer(
    help=(
        "Rendering and delivery."
    ),
    epilog=(
        "Special-format preset workflow:\n"
        "  1. Use `render preset-save` to capture current settings, or `render export-preset` to export a template.\n"
        "  2. Exported `.drpx` render presets are bundle directories that contain XML.\n"
        "  3. Edit that XML when you need a custom deliver variant, and rename the XML file if you want a new preset name.\n"
        "  4. Re-import with `render import-preset`, then `render preset-load`, `render add`, and `render start`."
    ),
)


def _require_sdk_render_guard(conn: Any) -> None:
    """Enforce the bridge-issued exact timeline precondition when present."""
    timeline_ops.require_sdk_mutation_guard(conn)


def _set_and_verify_render_mode(conn: Any, mode: int) -> int:
    applied = conn.project.SetCurrentRenderMode(mode)
    actual = conn.project.GetCurrentRenderMode()
    if applied is False or actual != mode:
        raise APICallFailed(
            "Failed to apply the requested render mode.",
            details={"requested_mode": mode, "actual_mode": actual},
        )
    return actual


def _bundled_transcript_preset_path() -> str:
    return os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "assets",
            "render-presets",
            "CutAgent Transcript.xml",
        ),
    )


def _load_json_object(value_or_path: str) -> dict[str, Any]:
    candidate = Path(value_or_path).expanduser()
    raw = candidate.read_text(encoding="utf-8") if candidate.is_file() else value_or_path
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "Expected a JSON object or a path to a JSON file.",
            details={"value_or_path": value_or_path, "error": str(exc)},
        ) from exc
    if not isinstance(data, dict):
        raise ValidationError(
            "Render settings JSON must be an object.",
            details={"value_or_path": value_or_path, "type": type(data).__name__},
        )
    return data


def _coerce_setting_value(value: str) -> Any:
    text = str(value)
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _probe_rate(value: Any) -> Optional[float]:
    try:
        numerator, denominator = (str(value).split("/", 1) + ["1"])[:2]
        result = float(numerator) / float(denominator)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return result if result > 0 else None


def _codec_family_matches(requested: str, actual: Any) -> bool:
    requested_key = str(requested).strip().lower().replace(".", "").replace(" ", "_").replace("-", "_")
    actual_key = str(actual or "").strip().lower().replace("-", "_")
    families = {
        "h264": ("h264", "avc", "avc1"),
        "h265": ("hevc", "h265", "hev1", "hvc1"),
        "apple_prores": ("prores",),
        "prores": ("prores",),
        "dnxhr": ("dnxhd", "dnxhr"),
        "av1": ("av1",),
        "linear_pcm": ("pcm",),
        "aac": ("aac",),
        "flac": ("flac",),
    }
    return any(actual_key == family or actual_key.startswith(f"{family}_") for family in families.get(requested_key, ()))


def _verify_exported_media(
    output_path: Path,
    *,
    expect_video: bool,
    expect_audio: bool,
    expected_codec: str,
    expected_width: Optional[int] = None,
    expected_height: Optional[int] = None,
    expected_fps: Optional[float] = None,
) -> dict[str, Any]:
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(output_path, os.O_RDONLY | no_follow)
    except OSError as exc:
        raise ValidationError("Render export did not create the exact requested non-empty file.", details={"path": str(output_path)}) from exc
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)

        def assert_identity() -> None:
            current = os.fstat(descriptor)
            path_stat = os.lstat(output_path)
            if (
                not os.path.isfile(output_path)
                or os.path.islink(output_path)
                or opened.st_size < 1
                or (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns) != identity
                or (path_stat.st_dev, path_stat.st_ino, path_stat.st_size) != identity[:3]
            ):
                raise ValidationError("Rendered output identity changed during verification.", details={"path": str(output_path)})

        assert_identity()
        probe_input = "pipe:0" if os.name == "nt" else f"/dev/fd/{descriptor}"
        command = [
            resolve_tool("ffprobe"), "-v", "error", "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,channels",
            "-of", "json", probe_input,
        ]
        try:
            if os.name == "nt":
                with os.fdopen(os.dup(descriptor), "rb") as probe_stream:
                    completed = subprocess.run(
                        command, stdin=probe_stream, capture_output=True, text=True, check=True, timeout=30,
                    )
            else:
                completed = subprocess.run(
                    command, pass_fds=(descriptor,), capture_output=True, text=True, check=True, timeout=30,
                )
            probed = json.loads(completed.stdout)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            raise ValidationError("FFprobe could not validate the rendered output.", details={"path": str(output_path)}) from exc
        assert_identity()
        streams = probed.get("streams") if isinstance(probed, dict) else None
        streams = streams if isinstance(streams, list) else []
        video_streams = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"]
        audio_streams = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "audio"]
        if expect_video != bool(video_streams) or expect_audio != bool(audio_streams):
            raise ValidationError(
                "Rendered output streams do not match the requested delivery settings.",
                details={"expected_video": expect_video, "expected_audio": expect_audio},
            )
        selected_stream = video_streams[0] if expect_video else audio_streams[0]
        if not _codec_family_matches(expected_codec, selected_stream.get("codec_name")):
            raise ValidationError("Rendered output codec does not match the requested codec family.")
        try:
            duration = float(probed.get("format", {}).get("duration"))
        except (TypeError, ValueError):
            duration = 0
        if duration <= 0:
            raise ValidationError("FFprobe did not confirm a positive rendered duration.")
        if expect_video:
            video_stream = video_streams[0]
            if not isinstance(video_stream.get("width"), int) or not isinstance(video_stream.get("height"), int):
                raise ValidationError("FFprobe did not confirm rendered video dimensions.")
            if expected_width is not None and (video_stream["width"] != expected_width or video_stream["height"] != expected_height):
                raise ValidationError("Rendered video dimensions do not match the requested settings.")
            delivered_fps = _probe_rate(video_stream.get("avg_frame_rate"))
            if delivered_fps is None:
                raise ValidationError("FFprobe did not confirm the rendered frame rate.")
            if expected_fps is not None and abs(delivered_fps - expected_fps) > 0.01:
                raise ValidationError("Rendered frame rate does not match the requested settings.")
        digest = hashlib.sha256()
        os.lseek(descriptor, 0, os.SEEK_SET)
        offset = 0
        while offset < opened.st_size:
            chunk = os.read(descriptor, min(1024 * 1024, opened.st_size - offset))
            if not chunk:
                raise ValidationError("Rendered output ended before its verified size.", details={"path": str(output_path)})
            digest.update(chunk)
            offset += len(chunk)
        assert_identity()
        return {
            "path": str(output_path),
            "size_bytes": opened.st_size,
            "sha256": f"sha256:{digest.hexdigest()}",
            "duration_seconds": duration,
            "video_stream": video_streams[0] if video_streams else None,
            "audio_stream": audio_streams[0] if audio_streams else None,
        }
    finally:
        os.close(descriptor)


@app.command("presets")
@handle_errors
def presets():
    """List available render presets."""
    conn = get_connection(require_project=True)
    preset_list = render_engine.get_render_presets(conn)
    if not preset_list:
        output([])
        return
    rows = [{"name": p} for p in preset_list]
    output(rows, columns=[("name", "Preset")], title="Render Presets", quiet_key="name")


@app.command("formats")
@handle_errors
def formats(
    media: str = typer.Option("video", "--media", help="Format inventory: video or audio."),
):
    """List available video or audio render formats."""
    enforce_mutation_policy("render.formats", intended_engine="api_native", mutating=False)
    conn = get_connection(require_project=True)
    media_kind = str(media).strip().lower()
    if media_kind not in {"video", "audio"}:
        raise ValidationError("Render format media must be 'video' or 'audio'.", details={"media": media})
    fmt_dict = (
        render_engine.get_audio_render_formats(conn)
        if media_kind == "audio"
        else render_engine.get_render_formats(conn)
    )
    if fmt_dict:
        if media_kind == "audio":
            rows = [
                {"format": k, "extension": v, "media": "audio", "source": "resolve_api"}
                for k, v in sorted(fmt_dict.items(), key=lambda item: str(item[0]).casefold())
            ]
            output(rows, columns=[("format", "Format"), ("extension", "Extension"), ("media", "Media"), ("source", "Source")])
        else:
            rows = [
                {"format": k, "description": v, "source": "resolve_api"}
                for k, v in sorted(fmt_dict.items(), key=lambda item: str(item[0]).casefold())
            ]
            output(rows, columns=[("format", "Format"), ("description", "Description"), ("source", "Source")])
    else:
        output([])


@app.command("codecs")
@handle_errors
def codecs(
    format_name: str = typer.Argument(..., help="Format name (e.g., mp4, QuickTime)"),
    media: str = typer.Option("video", "--media", help="Codec inventory: video or audio."),
):
    """List available video or audio codecs for a format."""
    conn = get_connection(require_project=True)
    media_kind = str(media).strip().lower()
    if media_kind not in {"video", "audio"}:
        raise ValidationError("Render codec media must be 'video' or 'audio'.", details={"media": media})
    codec_dict = (
        render_engine.get_audio_render_codecs(conn, format_name)
        if media_kind == "audio"
        else render_engine.get_render_codecs(conn, format_name)
    )
    if codec_dict:
        rows = [{"codec": k, "description": v, **({"media": "audio"} if media_kind == "audio" else {})} for k, v in codec_dict.items()]
        columns = [("codec", "Codec"), ("description", "Description")]
        if media_kind == "audio":
            columns.append(("media", "Media"))
        output(rows, columns=columns)
    else:
        output([])


@app.command("settings-get")
@app.command("settings")
@handle_errors
def render_settings():
    """Show current render settings."""
    enforce_mutation_policy("render.settings_read", intended_engine="api_native", mutating=False)
    conn = get_connection(require_project=True)
    settings = render_engine.get_render_settings(conn)
    output(settings, title="Render Settings")


@app.command("settings-set")
@handle_errors
def settings_set(
    target: Optional[str] = typer.Option(None, "--target", help="Output directory"),
    format: Optional[str] = typer.Option(None, "--format", help="Output format (mp4, mov, etc.)"),
    codec: Optional[str] = typer.Option(None, "--codec", help="Codec (H.264, H.265, etc.)"),
    name: Optional[str] = typer.Option(None, "--name", help="Output filename"),
    width: Optional[int] = typer.Option(None, "--width"),
    height: Optional[int] = typer.Option(None, "--height"),
    fps: Optional[float] = typer.Option(None, "--fps"),
    video: Optional[bool] = typer.Option(None, "--video/--no-video"),
    audio: Optional[bool] = typer.Option(None, "--audio/--no-audio"),
    audio_codec: Optional[str] = typer.Option(None, "--audio-codec", help="Audio codec, e.g. Linear PCM"),
    audio_bit_depth: Optional[int] = typer.Option(None, "--audio-bit-depth", help="Audio bit depth"),
    audio_sample_rate: Optional[int] = typer.Option(None, "--audio-sample-rate", help="Audio sample rate in Hz"),
    full_timeline: bool = typer.Option(False, "--full-timeline", help="Select the full timeline render range"),
):
    """Configure render settings."""
    enforce_mutation_policy(
        "render.settings_write",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would update render settings.")
        return
    conn = get_connection(require_project=True)
    _require_sdk_render_guard(conn)
    render_engine.set_render_settings(
        conn,
        target=target,
        format=format,
        codec=codec,
        name=name,
        width=width,
        height=height,
        fps=fps,
        video=video,
        audio=audio,
        audio_codec=audio_codec,
        audio_bit_depth=audio_bit_depth,
        audio_sample_rate=audio_sample_rate,
        full_timeline=full_timeline,
    )
    success("Updated render settings.")


@app.command("settings-set-json")
@handle_errors
def settings_set_json(
    json_or_file: str = typer.Argument(..., help="JSON object or path to a JSON file"),
):
    """Set arbitrary Project.SetRenderSettings keys from JSON."""
    enforce_mutation_policy("render.settings_write", intended_engine="api_native", mutating=not is_dry_run())
    settings = _load_json_object(json_or_file)
    if is_dry_run():
        dry_run_message(f"Would update render settings keys: {', '.join(settings)}")
        return
    conn = get_connection(require_project=True)
    output(render_engine.set_render_settings_dict(conn, settings), title="Render Settings")


@app.command("settings-set-key")
@handle_errors
def settings_set_key(
    key: str = typer.Argument(..., help="Project.SetRenderSettings key"),
    value: str = typer.Argument(..., help="Value; booleans/numbers/JSON are coerced"),
):
    """Set one Project.SetRenderSettings key."""
    enforce_mutation_policy("render.settings_write", intended_engine="api_native", mutating=not is_dry_run())
    coerced = _coerce_setting_value(value)
    if is_dry_run():
        dry_run_message(f"Would set render setting {key}={coerced!r}")
        return
    conn = get_connection(require_project=True)
    output(render_engine.set_render_setting_key(conn, key, coerced), title="Render Settings")


@app.command("subtitles")
@handle_errors
def subtitles(
    enable: bool = typer.Option(True, "--enable/--disable", help="Enable or disable subtitle export"),
    subtitle_format: str = typer.Option(..., "--format", help="BurnIn|EmbeddedCaptions|SeparateFile"),
):
    """Configure subtitle export settings."""
    enforce_mutation_policy("render.settings_write", intended_engine="api_native", mutating=not is_dry_run())
    settings = {"ExportSubtitle": enable, "SubtitleFormat": subtitle_format}
    if is_dry_run():
        dry_run_message(f"Would set subtitle render settings: {settings}")
        return
    conn = get_connection(require_project=True)
    output(render_engine.set_render_settings_dict(conn, settings), title="Render Subtitles")


@app.command("alpha")
@handle_errors
def alpha(
    enable: bool = typer.Option(True, "--enable/--disable", help="Enable or disable alpha export"),
    mode: str = typer.Option("premultiplied", "--mode", help="premultiplied|straight"),
):
    """Configure alpha-channel export settings."""
    if mode not in {"premultiplied", "straight"}:
        raise ValidationError("Invalid alpha mode. Use premultiplied or straight.", details={"mode": mode})
    enforce_mutation_policy("render.settings_write", intended_engine="api_native", mutating=not is_dry_run())
    settings = {"ExportAlpha": enable, "AlphaMode": mode}
    if is_dry_run():
        dry_run_message(
            f"Would set alpha render settings: {settings}; enabling alpha may switch render format "
            "to QuickTime / Apple ProRes 4444 if the current format cannot carry alpha."
        )
        return
    conn = get_connection(require_project=True)
    data = render_engine.set_render_alpha_settings(conn, enable=enable, mode=mode)
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(data, title="Render Alpha")


@app.command("encoding")
@handle_errors
def encoding(
    profile: str = typer.Option(..., "--profile", help="Encoding profile name/value"),
    multi_pass: bool = typer.Option(False, "--multi-pass/--single-pass", help="Enable multi-pass encoding"),
    network_optimization: bool = typer.Option(False, "--network-optimization/--no-network-optimization", help="Enable network optimization"),
):
    """Configure common encoding flags."""
    enforce_mutation_policy("render.settings_write", intended_engine="api_native", mutating=not is_dry_run())
    settings = {
        "EncodingProfile": profile,
        "MultiPassEncode": multi_pass,
        "NetworkOptimization": network_optimization,
    }
    if is_dry_run():
        dry_run_message(f"Would set encoding render settings: {settings}")
        return
    conn = get_connection(require_project=True)
    output(render_engine.set_render_settings_dict(conn, settings), title="Render Encoding")


@app.command("archive-settings")
@handle_errors
def archive_settings(
    target: Optional[str] = typer.Option(None, "--target", help="Output directory"),
    name: Optional[str] = typer.Option(None, "--name", help="Output filename"),
    format: str = typer.Option("QuickTime", "--format", help="Archive container format"),
    codec: Optional[str] = typer.Option("Apple ProRes", "--codec", help="Archive video codec selector"),
    audio_codec: str = typer.Option("Linear PCM", "--audio-codec", help="Archive audio codec"),
    audio_bit_depth: int = typer.Option(32, "--audio-bit-depth", help="Audio bit depth"),
    audio_sample_rate: int = typer.Option(48000, "--audio-sample-rate", help="Audio sample rate in Hz"),
    width: Optional[int] = typer.Option(None, "--width"),
    height: Optional[int] = typer.Option(None, "--height"),
    fps: Optional[float] = typer.Option(None, "--fps"),
    separate_audio_tracks: bool = typer.Option(
        True,
        "--separate-audio-tracks/--main-mix-audio",
        help="Request separate embedded timeline audio tracks when DaVinci Resolve API supports it",
    ),
):
    """Configure high-quality archive render settings and report audio-track export limits."""
    enforce_mutation_policy(
        "render.archive_settings",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if audio_bit_depth <= 0:
        raise ValidationError("Audio bit depth must be positive.", details={"audio_bit_depth": audio_bit_depth})
    if audio_sample_rate <= 0:
        raise ValidationError("Audio sample rate must be positive.", details={"audio_sample_rate": audio_sample_rate})
    if is_dry_run():
        output(
            {
                "action": "render.archive_settings",
                "would_configure": True,
                "dry_run": True,
                "settings": {
                    "target": target,
                    "name": name,
                    "format": format,
                    "codec": codec,
                    "audio_codec": audio_codec,
                    "audio_bit_depth": audio_bit_depth,
                    "audio_sample_rate": audio_sample_rate,
                    "width": width,
                    "height": height,
                    "fps": fps,
                    "separate_audio_tracks": separate_audio_tracks,
                },
                "separate_embedded_audio_tracks_note": (
                    "DaVinci Resolve's public SetRenderSettings API does not expose the all-timeline-tracks embedded "
                    "audio mapping; live command reports this explicitly after applying public settings."
                ),
            },
            title="Archive Render Settings Plan",
        )
        return
    conn = get_connection(require_project=True)
    data = render_engine.set_archive_render_settings(
        conn,
        target=target,
        name=name,
        format=format,
        codec=codec,
        audio_codec=audio_codec,
        audio_bit_depth=audio_bit_depth,
        audio_sample_rate=audio_sample_rate,
        width=width,
        height=height,
        fps=fps,
        separate_audio_tracks=separate_audio_tracks,
    )
    output(data, title="Archive Render Settings")


@app.command("preset-load")
@handle_errors
def preset_load(
    name: str = typer.Argument(..., help="Preset name"),
):
    """Load a render preset."""
    enforce_mutation_policy(
        "render.preset_load",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(
            f"Would load render preset selector: {name}. "
            "At execution time this is resolved against `render presets --json`."
        )
        return
    conn = get_connection(require_project=True)
    result = render_engine.load_render_preset(conn, name)
    preset_name = result.get("preset") if isinstance(result, dict) else name
    if preset_name != name:
        success(f"Loaded preset: {preset_name} (selector: {name})")
    else:
        success(f"Loaded preset: {preset_name}")


@app.command("add")
@handle_errors
def add_job(
    mark_in: Optional[str] = typer.Option(None, "--in", help="In point (timecode)"),
    mark_out: Optional[str] = typer.Option(None, "--out", help="Out point (timecode)"),
):
    """Add a render job to the queue."""
    enforce_mutation_policy("render.add", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        conn = get_connection(require_timeline=bool(mark_in or mark_out))
        preview = render_engine.preview_add_render_job(conn, mark_in, mark_out)
        output(
            mutation_payload(
                action="render.add",
                target={"kind": "render_queue"},
                changed=False,
                would_enqueue=True,
                runtime_write_called=False,
                settings=preview["settings"],
                queue_size_before=preview["queue_size_before"],
                render_target=preview["target_dir"],
                render_name=preview["custom_name"],
                output_precondition_verified=preview["output_precondition_verified"],
                missing_settings=preview["missing_settings"],
                message="DRY-RUN: Would add render job to the queue.",
            )
        )
        return

    conn = get_connection(require_timeline=True)
    _require_sdk_render_guard(conn)
    job_id = render_engine.add_render_job(conn, mark_in, mark_out)
    output(
        mutation_payload(
            action="render.add",
            target={"kind": "render_queue", "job_id": job_id},
            job_id=job_id,
            runtime_write_called=True,
            message=f"Added render job: {job_id}",
        )
    )


@app.command("export-file")
@handle_errors
def export_timeline(
    output_path: str = typer.Argument(..., help="Exact output file path"),
    format: str = typer.Option(..., "--format", help="Output format (QuickTime, MP4, MXF OP1A, Wave, AIFF)"),
    codec: str = typer.Option(..., "--codec", help="Output codec"),
    width: Optional[int] = typer.Option(None, "--width"),
    height: Optional[int] = typer.Option(None, "--height"),
    fps: Optional[float] = typer.Option(None, "--fps"),
    video: bool = typer.Option(True, "--video/--no-video"),
    audio: bool = typer.Option(True, "--audio/--no-audio"),
):
    """Configure, enqueue, render, wait, and validate one exact timeline output."""
    enforce_mutation_policy("render.export_file", intended_engine="api_native", mutating=not is_dry_run())
    destination = Path(output_path).expanduser().resolve()
    if not destination.name or not destination.suffix:
        raise ValidationError("Render export requires an exact filename with an extension.", details={"path": str(destination)})
    if destination.exists():
        raise ValidationError("Render export refuses to overwrite an existing output.", details={"path": str(destination)})
    if (width is None) != (height is None):
        raise ValidationError("Render width and height must be supplied together.")
    if not video and not audio:
        raise ValidationError("Render export must enable video, audio, or both.")
    if is_dry_run():
        output(mutation_payload(
            action="render.export_file",
            target={"kind": "file", "path": str(destination)},
            changed=False,
            runtime_write_called=False,
            format=format,
            codec=codec,
            video=video,
            audio=audio,
            message="DRY-RUN: Would configure, enqueue, render, wait, and validate the exact output file.",
        ))
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(require_timeline=True)
    _require_sdk_render_guard(conn)
    job_id: Optional[str] = None
    try:
        _set_and_verify_render_mode(conn, 1)
        _require_sdk_render_guard(conn)
        render_engine.set_render_settings(
            conn,
            target=str(destination.parent),
            format=format,
            codec=codec,
            name=destination.stem,
            width=width,
            height=height,
            fps=fps,
            video=video,
            audio=audio,
            full_timeline=True,
        )
        settings_readback = render_engine.get_render_settings(conn)
        if "SelectAllFrames" not in settings_readback:
            # Some native versions expose only format/mode getters. Read the
            # existing preset snapshot instead of treating an absent value as
            # either successful configuration or an explicit False.
            snapshot = render_engine._snapshot_render_context(conn)
            try:
                native_settings = snapshot.get("restore_settings", snapshot.get("settings", {}))
                settings_readback = {
                    **settings_readback,
                    "render_mode": snapshot.get("render_mode"),
                    "SelectAllFrames": native_settings.get("SelectAllFrames"),
                }
            finally:
                if snapshot.get("custody") == "render_preset_export":
                    render_engine._discard_render_context_preset_snapshot(conn, snapshot)
        if settings_readback.get("render_mode") != 1 or settings_readback.get("SelectAllFrames") is not True:
            raise APICallFailed(
                "Render export preconditions did not read back as single-clip full-timeline mode.",
                details={"required_mode": 1, "required_select_all_frames": True},
            )
        _require_sdk_render_guard(conn)
        job_id = render_engine.add_render_job(conn)
        _require_sdk_render_guard(conn)
        render_engine.start_rendering(conn, job_id, wait=True)
        artifact = _verify_exported_media(
            destination,
            expect_video=video,
            expect_audio=audio,
            expected_codec=codec,
            expected_width=width,
            expected_height=height,
            expected_fps=fps,
        )
    except Exception:
        if job_id:
            try:
                render_engine.cancel_render(
                    conn,
                    job_id=job_id,
                    delete_queued=True,
                    require_exclusive_job=True,
                )
            except Exception:
                pass
        raise
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(mutation_payload(
        action="render.export_file",
        target={"kind": "file", "path": str(destination)},
        job_id=job_id,
        runtime_write_called=True,
        verification_status="verified",
        artifact=artifact,
        message=f"Rendered and validated: {destination}",
    ))


@app.command("jobs")
@handle_errors
def list_jobs():
    """List render jobs in the queue."""
    conn = get_connection(require_project=True)
    rows = render_engine.get_render_jobs(conn)
    if not rows:
        output([])
        return
    output(rows, columns=[
        ("job_id", "Job ID"), ("status", "Status"), ("progress", "Progress"),
        ("target", "Target"), ("filename", "Filename"),
    ], title="Render Queue")


@app.command("start")
@handle_errors
def start(
    jobs: Optional[str] = typer.Option(None, "--jobs", help="Comma-separated job IDs"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for completion"),
):
    """Start rendering."""
    enforce_mutation_policy(
        "render.start",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(f"Would start rendering (jobs={jobs or 'all'}, wait={wait})")
        return
    conn = get_connection(require_project=True)
    _require_sdk_render_guard(conn)

    if get_output_mode() == "json":
        render_engine.start_rendering(conn, jobs, wait=wait)
        set_verification_status("verified" if wait else "not_requested")
        output(
            mutation_payload(
                action="render.start",
                changed=True,
                jobs=jobs,
                wait=wait,
                started=True,
                completed=wait,
                message="Render complete." if wait else "Rendering started.",
            )
        )
        return

    if not wait:
        render_engine.start_rendering(conn, jobs, wait=False)
        success("Rendering started.")
        return

    # Wait with progress bar
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Rendering...", total=100)

        def update_progress(pct, status):
            progress.update(task, completed=pct, description=f"Rendering ({status})...")

        try:
            render_engine.start_rendering(conn, jobs, wait=True, progress_callback=update_progress)
            progress.update(task, completed=100)
            success("Render complete!")
        except Exception:
            progress.update(task, completed=100)
            raise


@app.command("stop")
@handle_errors
def stop():
    """Stop rendering."""
    enforce_mutation_policy(
        "render.cancel",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would stop rendering.")
        return
    conn = get_connection(require_project=True)
    render_engine.stop_rendering(conn)
    success("Stopped rendering.")


@app.command("status")
@handle_errors
def render_status(
    job_id: Optional[str] = typer.Option(None, "--job", help="Specific job ID"),
):
    """Show render status."""
    conn = get_connection(require_project=True)
    status = render_engine.get_render_status(conn, job_id)
    output(status)


@app.command("job-status")
@handle_errors
def job_status(
    job_id: str = typer.Argument(..., help="Render job ID"),
):
    """Show status for a single render job."""
    conn = get_connection(require_project=True)
    output(render_engine.get_render_status(conn, job_id))


@app.command("delete")
@handle_errors
def delete_job(
    job_id: Optional[str] = typer.Option(None, "--job", help="Job ID to delete"),
    all: bool = typer.Option(False, "--all", help="Delete all jobs"),
):
    """Delete render jobs."""
    if not job_id and not all:
        raise ValidationError(
            "Provide either --job or --all.",
            details={"job_id": job_id, "all": all},
        )
    if job_id and all:
        raise ValidationError(
            "Provide either --job or --all, not both.",
            details={"job_id": job_id, "all": all},
        )
    enforce_mutation_policy(
        "render.queue_delete",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        if all:
            dry_run_message("Would delete all render jobs.")
        else:
            dry_run_message(
                f"Would delete render job selector: {job_id}. "
                "At execution time this is resolved as an exact JobId first, then a 1-based queue index."
            )
        return

    conn = get_connection(require_project=True)
    _require_sdk_render_guard(conn)
    result = render_engine.delete_render_job(conn, job_id, all)
    if all:
        success("Deleted all render jobs.")
    else:
        resolved_job_id = result.get("job_id") if isinstance(result, dict) else job_id
        if resolved_job_id != str(job_id):
            success(f"Deleted job: {resolved_job_id} (selector: {job_id})")
        else:
            success(f"Deleted job: {resolved_job_id}")


@app.command("audio")
@handle_errors
def render_audio(
    output_path: str = typer.Argument(..., help="Output file path"),
    format: str = typer.Option("Wave", help="Audio format"),
    codec: str = typer.Option("Linear PCM", help="Audio codec"),
    bitdepth: int = typer.Option(16, help="Bit depth"),
    samplerate: int = typer.Option(48000, help="Sample rate"),
):
    """Render audio only from the timeline."""
    enforce_mutation_policy(
        "render.audio_only",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(
            "Would render timeline audio to "
            f"{output_path} with format={format}, codec={codec}, bitdepth={bitdepth}, samplerate={samplerate}."
        )
        return
    conn = get_connection(require_timeline=True)
    if get_output_mode() == "json":
        result_path = render_engine.render_audio(
            conn, output_path, format, codec, bitdepth, samplerate, None
        )
        set_verification_status("verified")
        output(
            mutation_payload(
                action="render.audio",
                target={"kind": "file", "path": result_path},
                verification_status="verified",
                output_path=result_path,
                message=f"Audio rendered to: {result_path}",
            )
        )
        return

    # Wait with progress bar
    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as prog:
        task = prog.add_task("Rendering audio...", total=100)

        def update_progress(pct):
            prog.update(task, completed=pct)

        result_path = render_engine.render_audio(
            conn, output_path, format, codec, bitdepth, samplerate, update_progress
        )
        prog.update(task, completed=100)

    set_verification_status("verified")
    success(f"Audio rendered to: {result_path}")


@app.command("transcript-audio")
@handle_errors
def render_transcript_audio(
    output_path: str = typer.Argument(..., help="Output transcript audio file path"),
    preset_path: str = typer.Option(_bundled_transcript_preset_path(), "--preset-path", help="Path to transcript render preset XML"),
    preset_name: str = typer.Option("CutAgent Transcript", "--preset-name", help="Imported render preset name"),
):
    """Render transcript-ready audio from the active timeline and restore the previous Deliver context."""
    enforce_mutation_policy(
        "render.audio_only",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        if not os.path.exists(preset_path):
            raise ValidationError(
                "Render preset path not found.",
                details={"path": preset_path},
            )
        dry_run_message(
            "Would render transcript-ready audio to "
            f"{output_path} using preset '{preset_name}' from {preset_path}; "
            "would clear/refresh the render queue, import/load the preset, add and start a render job, wait for completion, and restore Deliver context."
        )
        return
    conn = get_connection(require_timeline=True)
    data = render_engine.render_transcript_audio(
        conn,
        output_path=output_path,
        preset_path=preset_path,
        preset_name=preset_name,
    )
    output(data, title="Transcript Audio Render")


# --- Render Mode ---

mode_app = typer.Typer(help="Render mode management.")
app.add_typer(mode_app, name="mode")


@mode_app.command("get")
@handle_errors
def mode_get():
    """Get current render mode."""
    conn = get_connection(require_project=True)
    mode = conn.project.GetCurrentRenderMode()
    mode_str = "individual" if mode == 0 else "single" if mode == 1 else f"unknown ({mode})"
    output({"mode": mode, "description": mode_str})


@mode_app.command("set")
@handle_errors
def mode_set(
    mode: str = typer.Argument(..., help="Render mode: individual (0) or single (1)"),
):
    """Set render mode."""
    enforce_mutation_policy("render.mode_set", intended_engine="api_native", mutating=not is_dry_run())

    # Parse mode
    mode_int = None
    if mode.lower() in ["individual", "0"]:
        mode_int = 0
    elif mode.lower() in ["single", "1"]:
        mode_int = 1
    else:
        from ..errors import ValidationError
        raise ValidationError(f"Invalid mode '{mode}'. Use 'individual' or 'single'.", details={"mode": mode})

    mode_str = "individual" if mode_int == 0 else "single"
    if is_dry_run():
        output(
            mutation_payload(
                action="render.mode.set",
                target={"kind": "render_mode"},
                changed=False,
                runtime_write_called=False,
                mode=mode_int,
                description=mode_str,
                message=f"DRY-RUN: Would set render mode to: {mode_str}.",
            )
        )
        return

    conn = get_connection(require_timeline=True)
    _require_sdk_render_guard(conn)
    actual = _set_and_verify_render_mode(conn, mode_int)
    output(mutation_payload(
        action="render.mode.set",
        target={"kind": "render_mode"},
        changed=True,
        runtime_write_called=True,
        mode=actual,
        description=mode_str,
        message=f"Set render mode to: {mode_str}.",
    ))


# --- Render Resolutions ---

@app.command("resolutions")
@handle_errors
def resolutions(
    format_name: Optional[str] = typer.Argument(None, help="Format (e.g., mp4, QuickTime)"),
    codec: Optional[str] = typer.Argument(None, help="Codec (e.g., H.264, H.265)"),
):
    """List available render resolutions."""
    enforce_mutation_policy("render.resolutions", intended_engine="api_native", mutating=False)
    conn = get_connection(require_project=True)
    resolutions = render_engine.get_render_resolutions(conn, format_name, codec)
    
    if not resolutions:
        output([])
        return
    
    rows = []
    for i, res in enumerate(resolutions, 1):
        if isinstance(res, dict):
            rows.append({"index": i, **res})
        else:
            rows.append({"index": i, "resolution": str(res)})
    
    output(rows, title="Available Resolutions")


# --- Save Preset ---

@app.command(
    "preset-save",
    help=(
        "Save current render settings as a reusable preset you can export, edit, and import again.\n\n"
        "Use this to capture a custom deliver configuration before exporting it as a `.drpx` bundle "
        "or reloading it later with `render preset-load`."
    ),
)
@handle_errors
def preset_save(
    name: str = typer.Argument(..., help="Preset name"),
):
    """Save current render settings as a new preset.

    Use this when you want to capture a custom deliver configuration before
    exporting it as a `.drpx` preset bundle or reloading it later with
    `render preset-load`.
    """
    enforce_mutation_policy("render.preset_save", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            mutation_payload(
                action="render.preset_save",
                target={"kind": "render_preset", "name": name},
                changed=False,
                runtime_write_called=False,
                preset=name,
                message=f"DRY-RUN: Would save current render settings as preset: {name}.",
            )
        )
        return

    conn = get_connection(require_project=True)
    save_render_preset(conn, name)
    success(f"Saved preset: {name}")


@app.command("preset-update")
@handle_errors
def preset_update(
    name: str = typer.Argument(..., help="Exact existing render preset name"),
):
    """Replace an existing preset with current render settings and verify its exported content."""
    enforce_mutation_policy("render.preset_save", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would update render preset: {name}")
        return
    output(update_render_preset(get_connection(require_project=True), name), title="Render Preset Update")


@app.command("preset-delete")
@handle_errors
def preset_delete(
    name: str = typer.Argument(..., help="Preset name"),
):
    """Delete a render preset when DaVinci Resolve exposes the API."""
    enforce_mutation_policy("render.preset_save", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would delete render preset: {name}")
        return
    conn = get_connection(require_project=True)
    output(render_engine.delete_render_preset(conn, name), title="Render Preset Delete")


burnin_app = typer.Typer(help="Render burn-in preset operations.")
app.add_typer(burnin_app, name="burnin")


@burnin_app.command("import")
@handle_errors
def burnin_import(
    path: str = typer.Argument(..., help="Burn-in preset file path"),
):
    """Import a burn-in preset."""
    enforce_mutation_policy("render.burnin_preset_import_export", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would import burn-in preset from: {path}")
        return
    conn = get_connection(require_project=False)
    output(render_engine.import_burnin_preset(conn, path), title="Burn-In Preset Import")


@burnin_app.command("export")
@handle_errors
def burnin_export(
    name: str = typer.Argument(..., help="Burn-in preset name"),
    path: str = typer.Argument(..., help="Export path"),
):
    """Export a burn-in preset."""
    enforce_mutation_policy("render.burnin_preset_import_export", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would export burn-in preset '{name}' to: {path}")
        return
    conn = get_connection(require_project=False)
    output(render_engine.export_burnin_preset(conn, name, path), title="Burn-In Preset Export")


@burnin_app.command("load")
@handle_errors
def burnin_load(
    name: str = typer.Argument(..., help="Burn-in preset name"),
):
    """Load a burn-in preset for rendering."""
    enforce_mutation_policy("render.burnin_preset_import_export", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would load burn-in preset: {name}")
        return
    conn = get_connection(require_project=True)
    output(render_engine.load_burnin_preset(conn, name), title="Burn-In Preset Load")


@app.command("wait")
@handle_errors
def wait_for_render(
    jobs: Optional[str] = typer.Option(None, "--jobs", help="Comma-separated job IDs"),
    timeout_s: Optional[float] = typer.Option(None, "--timeout-s", help="Optional timeout"),
    poll_ms: int = typer.Option(500, "--poll-ms", help="Polling interval in milliseconds"),
):
    """Wait for render completion (canonical blocking wait)."""
    conn = get_connection(require_project=True)
    status = render_engine.wait_for_render(conn, jobs=jobs, timeout_s=timeout_s, poll_ms=poll_ms)
    if get_output_mode() == "json":
        set_verification_status("verified")
        output(
            mutation_payload(
                action="render.wait",
                changed=False,
                jobs=jobs,
                timeout_s=timeout_s,
                poll_ms=poll_ms,
                status=status,
                completed=True,
                message="Render complete.",
            )
        )
        return
    success("Render complete.")


@app.command("cancel")
@handle_errors
def cancel(
    job: Optional[str] = typer.Option(None, "--job", help="Optional job ID to target"),
    delete_queued: bool = typer.Option(False, "--delete-queued", help="Delete queued job(s) as well"),
    require_exclusive_job: bool = typer.Option(False, "--require-exclusive-job", hidden=True),
):
    """Cancel active rendering."""
    enforce_mutation_policy("render.cancel", intended_engine="api_native", mutating=not is_dry_run())
    conn = get_connection(require_project=True)
    _require_sdk_render_guard(conn)
    if is_dry_run():
        preview = render_engine.preview_cancel_render(conn, job_id=job, delete_queued=delete_queued)
        output(
            mutation_payload(
                action="render.cancel",
                target={"kind": "render_queue", "job_id": preview["job_id"]},
                changed=False,
                runtime_write_called=False,
                would_cancel_active_render=preview["would_cancel_active_render"],
                would_delete_jobs=preview["would_delete_jobs"],
                requested_job=preview["requested_job"],
                job_id=preview["job_id"],
                delete_queued=delete_queued,
                available_jobs=preview["available_jobs"],
                message="DRY-RUN: Would cancel active rendering and optionally delete queued render jobs.",
            )
        )
        return

    data = render_engine.cancel_render(
        conn,
        job_id=job,
        delete_queued=delete_queued,
        require_exclusive_job=require_exclusive_job,
    )
    changed = bool(data.get("cancelled")) or bool(data.get("deleted_jobs"))
    output(
        mutation_payload(
            action="render.cancel",
            target={"kind": "render_queue", "job_id": data.get("job_id")},
            changed=changed,
            runtime_write_called=changed,
            **data,
        ),
        title="Render Cancel",
    )


@app.command("custom-range")
@handle_errors
def custom_range(
    in_ref: str = typer.Option(..., "--in", help="In reference"),
    out_ref: str = typer.Option(..., "--out", help="Out reference"),
    range_domain: str = typer.Option(
        "record",
        "--range-domain",
        help="Range reference domain: record adds the timeline start frame; absolute uses the parsed frame/timecode directly",
    ),
    start: bool = typer.Option(True, "--start/--no-start", help="Start render immediately"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for completion"),
):
    """Queue render for a custom range."""
    if range_domain.__class__.__name__ == "OptionInfo":
        range_domain = "record"
    enforce_mutation_policy(
        "render.custom_range",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if wait and not start:
        raise ValidationError(
            "Cannot wait for a custom-range render when --no-start is set.",
            details={"start": start, "wait": wait},
        )
    conn = get_connection(require_timeline=True)
    if is_dry_run():
        preview = render_engine.preview_add_render_job(conn, in_ref, out_ref, range_domain=range_domain)
        output(
            mutation_payload(
                action="render.custom_range",
                target={"kind": "render_queue"},
                changed=False,
                runtime_write_called=False,
                would_enqueue=True,
                would_start=start,
                would_wait=wait,
                settings=preview["settings"],
                range_domain=preview.get("range_domain"),
                queue_size_before=preview["queue_size_before"],
                render_target=preview["target_dir"],
                render_name=preview["custom_name"],
                output_precondition_verified=preview["output_precondition_verified"],
                missing_settings=preview["missing_settings"],
                message="DRY-RUN: Would queue a custom-range render job.",
            )
        )
        return

    data = render_engine.render_custom_range(
        conn,
        mark_in=in_ref,
        mark_out=out_ref,
        start=start,
        wait=wait,
        range_domain=range_domain,
    )
    output(
        mutation_payload(
            action="render.custom_range",
            target={"kind": "render_queue", "job_id": data.get("job_id")},
            runtime_write_called=True,
            **data,
        ),
        title="Render Custom Range",
    )


@app.command("quick-export")
@handle_errors
def quick_export_cmd(
    preset: str = typer.Argument(..., help="Quick export preset name."),
    output_path: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory."),
):
    """Render using a quick export preset."""
    enforce_mutation_policy(
        "render.quick_export",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        return dry_run_message(
            f"Would quick-export with preset selector '{preset}'. "
            "At execution time this is resolved against `render quick-export-presets --json`."
        )
    conn = get_connection()
    result = render_engine.render_with_quick_export(conn, preset, output_path=output_path)
    output(result)


@app.command("quick-export-presets")
@handle_errors
def quick_export_presets_cmd():
    """List available quick export presets."""
    conn = get_connection()
    presets = render_engine.get_quick_export_presets(conn)
    output(presets)


@app.command(
    "import-preset",
    help=(
        "Import a render preset from an exported `.drpx` bundle or a direct XML preset path.\n\n"
        "Exported `.drpx` render presets are bundle directories that contain XML. This command "
        "accepts either the bundle path itself or the XML path inside it, so export -> edit XML -> "
        "import round-trips work reliably. When importing a modified preset variant, rename the XML "
        "file to the new preset name first."
    ),
)
@handle_errors
def import_preset_cmd(
    path: str = typer.Argument(
        ...,
        help="Path to an exported `.drpx` preset bundle directory or a direct XML preset file.",
    ),
):
    """Import a render preset from file.

    Exported render presets are `.drpx` bundle directories that contain an XML
    preset file. This command accepts either the bundle path itself or the XML
    path inside the bundle, which makes export -> edit XML -> import round-trips
    work reliably.
    """
    enforce_mutation_policy(
        "render.preset_import_export",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(
            f"Would import render preset from {path}. "
            "At execution time this is resolved as an XML preset file or `.drpx` bundle."
        )
        return
    conn = get_connection()
    result = render_engine.import_render_preset(conn, path)
    output(result)


@app.command(
    "export-preset",
    help=(
        "Export a render preset as a `.drpx` bundle that you can inspect, edit, and re-import.\n\n"
        "DaVinci Resolve exports render presets as bundle directories containing XML. Use this when you want "
        "a template for a special deliver format instead of guessing unsupported render flags. "
        "If you plan to import a modified variant, rename the XML file inside the bundle to the "
        "new preset name first."
    ),
)
@handle_errors
def export_preset_cmd(
    name: str = typer.Argument(..., help="Preset name."),
    path: str = typer.Argument(..., help="Output `.drpx` bundle path."),
):
    """Export a render preset to file.

    DaVinci Resolve exports render presets as `.drpx` bundle directories containing XML.
    That XML can be used as a template for special deliver formats before running
    `render import-preset` and `render preset-load`.
    """
    enforce_mutation_policy(
        "render.preset_import_export",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(
            f"Would export render preset selector '{name}' to {path}. "
            "At execution time this is resolved against `render presets --json`."
        )
        return
    conn = get_connection()
    result = render_engine.export_render_preset(conn, name, path)
    output(result)
