"""Rendered before/after evidence for consequential timeline-item mutations."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from ..errors import APICallFailed
from ..external_tools import resolve_tool
from ..utils.timecode import seconds_to_timecode
from . import render_engine, timeline_ops, version_ops
from .fusion_setting_canonical import canonicalize_fusion_tools
from .mutation_target import (
    TimelineItemTarget,
    revalidate_timeline_item_target,
    resolve_timeline_item_target,
)

_WIDTH = 96
_HEIGHT = 54


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_fusion_setting_tools(raw: bytes) -> bytes:
    return canonicalize_fusion_tools(raw)


def _graph_states_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    keys = ("count", "names", "graphs", "canonical_raw_exports")
    return all(left.get(key) == right.get(key) for key in keys)


def _persisted_graph_states_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    # The API snapshot is useful independent evidence but is not complete: it
    # can omit tool attributes, modifiers, expressions and animation samples.
    # The parsed Tools value retains that complete semantic surface while
    # accepting DaVinci Resolve's non-semantic table reserialization.
    keys = ("count", "names", "graphs", "canonical_raw_exports")
    return all(left.get(key) == right.get(key) for key in keys)


def _job_id(job: Any) -> str | None:
    if not isinstance(job, dict):
        return None
    value = (
        job.get("JobId") or job.get("JobID") or job.get("jobId") or job.get("job_id")
    )
    return str(value) if value not in (None, "") else None


def _jobs(conn: Any) -> list[dict[str, Any]]:
    getter = getattr(getattr(conn, "project", None), "GetRenderJobList", None)
    if not callable(getter):
        raise APICallFailed(
            "GetRenderJobList is required for authoritative rendered effect proof."
        )
    rows = getter()
    if not isinstance(rows, list):
        raise APICallFailed(
            "Render queue readback is not a list; job ownership cannot be proven."
        )
    return [row for row in rows if isinstance(row, dict)]


def _render_output(conn: Any, directory: Path, base_name: str, job_id: str) -> Path:
    candidates: list[Path] = []
    for job in _jobs(conn):
        if _job_id(job) != job_id:
            continue
        raw = (
            job.get("OutputFilename")
            or job.get("OutputFileName")
            or job.get("Filename")
        )
        if raw:
            candidate = Path(str(raw))
            candidates.append(
                candidate if candidate.is_absolute() else directory / candidate
            )
    candidates.extend(sorted(directory.glob(f"{base_name}*")))
    outputs = sorted(
        {
            candidate.resolve()
            for candidate in candidates
            if candidate.is_file() and candidate.stat().st_size > 0
        }
    )
    if len(outputs) != 1:
        raise APICallFailed(
            "One-frame Deliver render did not produce exactly one readable output.",
            details={
                "directory": str(directory),
                "base_name": base_name,
                "job_id": job_id,
                "outputs": [str(path) for path in outputs],
            },
        )
    return outputs[0]


def _verify_job_range(conn: Any, job_id: str, frame: int) -> dict[str, Any]:
    matches = [row for row in _jobs(conn) if _job_id(row) == job_id]
    if len(matches) != 1:
        raise APICallFailed(
            "Exact Deliver proof job disappeared before range readback.",
            details={"job_id": job_id, "match_count": len(matches)},
        )
    job = matches[0]
    try:
        mark_in = int(job["MarkIn"])
        mark_out = int(job["MarkOut"])
    except (KeyError, TypeError, ValueError) as exc:
        raise APICallFailed(
            "Deliver proof job does not expose exact frame-range readback.",
            details={"job_id": job_id, "job": job},
        ) from exc
    if mark_in != frame or mark_out != frame:
        raise APICallFailed(
            "Deliver proof job range does not match the requested one-frame range.",
            details={
                "job_id": job_id,
                "expected_frame": frame,
                "mark_in": mark_in,
                "mark_out": mark_out,
            },
        )
    return {"mark_in": mark_in, "mark_out": mark_out}


def _target_graph_state(target: TimelineItemTarget) -> dict[str, Any]:
    from . import clip_ops, color_ops

    count = int(target.item.GetFusionCompCount())
    names = clip_ops._fusion_comp_name_list(target.item)
    if count < 0 or len(names) != count:
        raise APICallFailed(
            "Exact Fusion composition identity is unavailable for render custody.",
            details={"count": count, "names": names},
        )
    graphs = []
    raw_exports = []
    canonical_raw_exports = []
    raw_payloads = []
    with tempfile.TemporaryDirectory(
        prefix="cutagent-render-graph-custody-"
    ) as raw_dir:
        for index in range(1, count + 1):
            comp = target.item.GetFusionCompByIndex(index)
            graph = color_ops._snapshot_comp_graph(comp) if comp is not None else None
            if (
                not isinstance(graph, dict)
                or not isinstance(graph.get("tools"), dict)
                or not graph["tools"]
            ):
                raise APICallFailed(
                    "Exact Fusion graph readback is unavailable for render custody.",
                    details={"comp_index": index},
                )
            raw_path = Path(raw_dir) / f"composition-{index}.setting"
            exporter = getattr(target.item, "ExportFusionComp", None)
            if not callable(exporter) or exporter(str(raw_path), index) is not True:
                raise APICallFailed(
                    "Raw Fusion composition export is unavailable for render custody.",
                    details={"comp_index": index},
                )
            if not raw_path.is_file() or raw_path.stat().st_size <= 0:
                raise APICallFailed(
                    "Raw Fusion composition export is empty for render custody.",
                    details={"comp_index": index},
                )
            raw = raw_path.read_bytes()
            canonical = _canonical_fusion_setting_tools(raw)
            graphs.append(graph)
            raw_exports.append(
                {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            )
            canonical_raw_exports.append(
                {
                    "bytes": len(canonical),
                    "sha256": hashlib.sha256(canonical).hexdigest(),
                }
            )
            raw_payloads.append(raw)
    return {
        "count": count,
        "names": names,
        "graphs": graphs,
        "raw_exports": raw_exports,
        "canonical_raw_exports": canonical_raw_exports,
        "_raw_payloads": raw_payloads,
    }


def _resolve_reopened_target(
    conn: Any, target: TimelineItemTarget
) -> TimelineItemTarget:
    if target.item_id:
        fresh = resolve_timeline_item_target(conn, item_id=target.item_id)
    else:
        fresh = resolve_timeline_item_target(
            conn,
            track=target.track_index,
            record_frame=target.start,
        )
    expected = target.public()
    observed = fresh.public()
    identity_keys = (
        "timeline_id",
        "timeline_item_id",
        "track_type",
        "track_index",
        "name",
        "start",
        "end",
    )
    if any(expected.get(key) != observed.get(key) for key in identity_keys):
        raise APICallFailed(
            "Full project checkpoint restore did not recover the exact render target.",
            details={"expected": expected, "observed": observed},
            recoverability="manual",
        )
    return fresh


def _persist_target_graph_before_checkpoint(
    conn: Any,
    target: TimelineItemTarget,
    graph_state: dict[str, Any],
) -> TimelineItemTarget:
    if graph_state.get("count") == 0:
        return target
    manager = getattr(conn, "project_manager", None)
    project = getattr(conn, "project", None)
    save = getattr(manager, "SaveProject", None)
    close = getattr(manager, "CloseProject", None)
    load = getattr(manager, "LoadProject", None)
    name_getter = getattr(project, "GetName", None)
    if not all(callable(method) for method in (save, close, load, name_getter)):
        raise APICallFailed(
            "Fusion graph persistence barrier is unavailable before rendered proof.",
            details={"possible_mutation": True},
            recoverability="manual",
        )
    project_name = str(name_getter() or "")

    def save_close_reopen(current: TimelineItemTarget) -> TimelineItemTarget:
        active_project = getattr(conn, "project", None)
        if not project_name or save() is not True or close(active_project) is not True:
            raise APICallFailed(
                "Fusion graph could not be saved and closed before rendered proof.",
                details={"project_name": project_name, "possible_mutation": True},
                recoverability="manual",
            )
        loaded = load(project_name)
        if loaded is None or loaded is False:
            raise APICallFailed(
                "Fusion graph project could not be reopened before rendered proof.",
                details={"project_name": project_name, "possible_mutation": True},
                recoverability="manual",
            )
        conn.refresh()
        return _resolve_reopened_target(conn, current)

    fresh = save_close_reopen(target)
    persisted = _target_graph_state(fresh)
    if (
        not _persisted_graph_states_equal(persisted, graph_state)
        and persisted.get("count") == 0
    ):
        _replay_rendered_graph(conn, fresh, graph_state)
        replayed = _target_graph_state(fresh)
        if not _graph_states_equal(replayed, graph_state):
            raise APICallFailed(
                "Fusion graph replay did not reproduce the exact pre-render graph.",
                recoverability="manual",
            )
        fresh = save_close_reopen(fresh)
        persisted = _target_graph_state(fresh)
    if not _persisted_graph_states_equal(persisted, graph_state):
        raise APICallFailed(
            "Fusion graph did not persist exactly across the save/reopen barrier.",
            details={
                "expected_count": graph_state.get("count"),
                "observed_count": persisted.get("count"),
                "expected_raw_exports": graph_state.get("raw_exports"),
                "observed_raw_exports": persisted.get("raw_exports"),
            },
            recoverability="manual",
        )
    return fresh


def _replay_rendered_graph(
    conn: Any, target: TimelineItemTarget, graph_state: dict[str, Any]
) -> None:
    payloads = graph_state.get("_raw_payloads")
    if (
        graph_state.get("count") != 1
        or not isinstance(payloads, list)
        or len(payloads) != 1
        or not isinstance(payloads[0], bytes)
        or int(target.item.GetFusionCompCount() or 0) != 0
    ):
        raise APICallFailed(
            "Exact rendered Fusion graph replay is unsupported for this target state.",
            details={
                "rendered_comp_count": graph_state.get("count"),
                "restored_comp_count": int(target.item.GetFusionCompCount() or 0),
            },
            recoverability="manual",
        )
    with tempfile.NamedTemporaryFile(suffix=".setting", delete=False) as handle:
        path = Path(handle.name)
        handle.write(payloads[0])
    try:
        importer = getattr(target.item, "ImportFusionComp", None)
        result = importer(str(path)) if callable(importer) else False
        if result is False:
            raise APICallFailed(
                "Exact visually proven Fusion graph could not be replayed after render custody restore.",
                recoverability="manual",
            )
    finally:
        path.unlink(missing_ok=True)


def _capture_deliver_frame(
    conn: Any,
    directory: Path,
    base_name: str,
    frame: int,
    *,
    target: TimelineItemTarget | None = None,
) -> dict[str, Any]:
    project = getattr(conn, "project", None)
    rendering = getattr(project, "IsRenderingInProgress", None)
    deleter = getattr(project, "DeleteRenderJob", None)
    stopper = getattr(project, "StopRendering", None)
    if not callable(rendering) or rendering() is not False:
        raise APICallFailed(
            "Cannot prove the Deliver queue is idle before rendered effect proof."
        )
    if not callable(deleter):
        raise APICallFailed(
            "DeleteRenderJob is required for non-destructive rendered effect proof."
        )
    if not callable(stopper):
        raise APICallFailed(
            "StopRendering is required for bounded rendered effect proof recovery."
        )

    checkpoint = None
    checkpoint_session = None
    graph_state = None
    if target is not None:
        manager = getattr(conn, "project_manager", None)
        if not callable(getattr(manager, "CloseProject", None)) or not callable(
            getattr(manager, "LoadProject", None)
        ):
            raise APICallFailed(
                "Exact full-project render custody is unavailable; refusing to change Deliver settings.",
                details={
                    "possible_mutation": False,
                    "missing_project_manager_apis": True,
                },
            )
        checkpoint_session = f"render-proof-{uuid.uuid4()}"
        graph_state = _target_graph_state(target)
        target = _persist_target_graph_before_checkpoint(conn, target, graph_state)
        graph_state = _target_graph_state(target)
        project = getattr(conn, "project", None)
        rendering = getattr(project, "IsRenderingInProgress", None)
        deleter = getattr(project, "DeleteRenderJob", None)
        stopper = getattr(project, "StopRendering", None)
        if not callable(rendering) or rendering() is not False:
            raise APICallFailed(
                "Cannot prove the rebound Deliver queue is idle before rendered effect proof."
            )
        if not callable(deleter) or not callable(stopper):
            raise APICallFailed(
                "Rebound Deliver job cleanup APIs are unavailable for rendered effect proof."
            )
        checkpoint = version_ops.create_checkpoint(
            conn,
            label=f"Internal one-frame render custody: {base_name}",
            kind="before_prompt",
            session_id=checkpoint_session,
        )
        snapshot_path = Path(str(checkpoint.get("snapshot_path") or ""))
        if (
            checkpoint.get("database_type") != "Disk"
            or not checkpoint.get("state_hash")
            or not snapshot_path.is_file()
        ):
            raise APICallFailed(
                "Exact full-project render custody is unavailable; refusing to change Deliver settings.",
                details={
                    "possible_mutation": False,
                    "checkpoint_id": checkpoint.get("id"),
                },
            )
    context = None
    before_jobs: list[dict[str, Any]] = []
    before_ids: set[str | None] = set()
    job_id: str | None = None
    primary_error: BaseException | None = None
    evidence: dict[str, Any] | None = None
    evidence_rebound_target: TimelineItemTarget | None = None
    try:
        context = render_engine._snapshot_render_context(conn)
        before_jobs = _jobs(conn)
        before_ids = {_job_id(row) for row in before_jobs}
        render_engine.set_render_settings(
            conn,
            target=str(directory),
            format="PNG",
            codec="RGB8",
            name=base_name,
            video=True,
            audio=False,
        )
        job_settings = render_engine._render_job_settings(
            conn, f"{frame}f", f"{frame}f", range_domain="absolute"
        )
        settings_setter = getattr(project, "SetRenderSettings", None)
        add_job = getattr(project, "AddRenderJob", None)
        with render_engine._with_required_page(conn, "deliver"):
            if (
                not callable(settings_setter)
                or settings_setter(job_settings) is not True
            ):
                raise APICallFailed(
                    "Failed to apply the exact one-frame Deliver range.",
                    details={"settings": job_settings},
                )
            if not callable(add_job):
                raise APICallFailed(
                    "AddRenderJob is required for authoritative rendered effect proof."
                )
            raw_job_id = add_job()
        after_add_ids = {_job_id(row) for row in _jobs(conn)}
        added_ids = {value for value in after_add_ids - before_ids if value}
        if len(added_ids) != 1 or raw_job_id in (None, False, ""):
            raise APICallFailed(
                "Exactly one owned one-frame Deliver render job was not created.",
                details={
                    "api_result": raw_job_id,
                    "before_job_ids": sorted(value for value in before_ids if value),
                    "added_job_ids": sorted(added_ids),
                },
            )
        job_id = next(iter(added_ids))
        if str(raw_job_id) != job_id:
            raise APICallFailed(
                "Deliver job API result does not match the exact queue delta.",
                details={"api_result": raw_job_id, "added_job_id": job_id},
            )
        range_readback = _verify_job_range(conn, job_id, frame)
        starter = getattr(project, "StartRendering", None)
        if not callable(starter) or starter([job_id]) is False:
            raise APICallFailed(
                "Failed to start authoritative one-frame Deliver render.",
                details={"job_id": job_id},
            )
        render_engine.wait_for_render(conn, jobs=job_id, timeout_s=120)
        path = _render_output(conn, directory, base_name, job_id)
        # Decode now. A successful process/job status alone is not visual proof.
        _rgb(path)
        evidence = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "job_id": job_id,
            "proof_kind": "deliver_one_frame_decoded_pixels",
            "authoritative": True,
            "range": {"domain": "absolute", **range_readback},
        }
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        cleanup_errors: list[dict[str, Any]] = []
        try:
            observed_delta = {
                value
                for value in ({_job_id(row) for row in _jobs(conn)} - before_ids)
                if value
            }
        except Exception as exc:
            observed_delta = set()
            cleanup_errors.append(
                {"phase": "discover_owned_render_jobs", "error": str(exc)}
            )
        expected_delta = {job_id} if job_id is not None else set()
        if observed_delta != expected_delta:
            cleanup_errors.append(
                {
                    "phase": "ambiguous_render_queue_delta",
                    "owned_job_id": job_id,
                    "observed_delta": sorted(observed_delta),
                }
            )
        # Never infer ownership from an ambiguous queue delta. Only the API ID
        # that already matched the unique post-AddRenderJob delta is deletable.
        cleanup_job_ids = [job_id] if job_id is not None else []
        for cleanup_job_id in cleanup_job_ids:
            try:
                render_active = rendering()
                if render_active is True:
                    render_engine.cancel_render(
                        conn,
                        job_id=cleanup_job_id,
                        delete_queued=True,
                        require_exclusive_job=True,
                    )
                elif render_active is False and deleter(cleanup_job_id) is False:
                    cleanup_errors.append(
                        {"phase": "delete_render_job", "result": False}
                    )
                elif not isinstance(render_active, bool):
                    cleanup_errors.append(
                        {"phase": "read_render_activity", "result": render_active}
                    )
                if cleanup_job_id in {_job_id(row) for row in _jobs(conn)}:
                    cleanup_errors.append(
                        {"phase": "verify_render_job_absent", "job_id": cleanup_job_id}
                    )
            except Exception as exc:
                cleanup_errors.append(
                    {
                        "phase": "delete_render_job",
                        "job_id": cleanup_job_id,
                        "error": str(exc),
                    }
                )
        if checkpoint is None:
            try:
                if context is not None:
                    render_engine._restore_render_context(conn, context)
            except Exception as exc:
                cleanup_errors.append(
                    {"phase": "restore_render_context", "error": str(exc)}
                )
        else:
            try:
                restored = version_ops.restore_checkpoint(
                    conn,
                    str(checkpoint["id"]),
                    expected_checkpoint_digest=version_ops.checkpoint_binding_digest(
                        checkpoint
                    ),
                )
                if restored.get("verified") is not True:
                    raise APICallFailed(
                        "Full project render custody restore was not verified."
                    )
                conn.refresh()
                status = version_ops.version_status(conn, include_private_identity=True)
                if status.get("state_hash") != checkpoint.get("state_hash"):
                    raise APICallFailed(
                        "Full project render custody state hash did not match.",
                        details={
                            "expected": checkpoint.get("state_hash"),
                            "observed": status.get("state_hash"),
                        },
                    )
                if context is not None:
                    if context.get("custody") == "render_preset_export":
                        with render_engine._with_required_page(conn, "deliver"):
                            render_engine._replay_render_context_from_preset(
                                conn, context, include_empty_target=False
                            )
                    else:
                        render_engine._restore_render_context(conn, context)
                    restored = version_ops.restore_checkpoint(
                        conn,
                        str(checkpoint["id"]),
                        expected_checkpoint_digest=version_ops.checkpoint_binding_digest(
                            checkpoint
                        ),
                    )
                    if restored.get("verified") is not True:
                        raise APICallFailed(
                            "Second full project render custody restore was not verified."
                        )
                    conn.refresh()
                    status = version_ops.version_status(
                        conn, include_private_identity=True
                    )
                    if status.get("state_hash") != checkpoint.get("state_hash"):
                        raise APICallFailed(
                            "Second full project render custody state hash did not match.",
                            details={
                                "expected": checkpoint.get("state_hash"),
                                "observed": status.get("state_hash"),
                            },
                        )
                restored_jobs = _jobs(conn)
                restored_job_ids = {_job_id(row) for row in restored_jobs}
                if restored_jobs != before_jobs:
                    raise APICallFailed(
                        "Full project render custody did not recover the exact render queue.",
                        details={
                            "expected_job_ids": sorted(
                                value for value in before_ids if value
                            ),
                            "observed_job_ids": sorted(
                                value for value in restored_job_ids if value
                            ),
                            "expected_job_count": len(before_jobs),
                            "observed_job_count": len(restored_jobs),
                        },
                    )
                rebound_target = _resolve_reopened_target(conn, target)
                if context is not None:
                    render_engine._verify_render_context_after_checkpoint(conn, context)
                restored_graph_state = _target_graph_state(rebound_target)
                if not _graph_states_equal(restored_graph_state, graph_state):
                    _replay_rendered_graph(conn, rebound_target, graph_state)
                    replayed_graph_state = _target_graph_state(rebound_target)
                    if not _graph_states_equal(replayed_graph_state, graph_state):
                        raise APICallFailed(
                            "Replayed visually proven Fusion graph did not match its exact captured state.",
                            details={
                                "expected_graph_sha256": hashlib.sha256(
                                    json.dumps(
                                        graph_state.get("graphs"),
                                        sort_keys=True,
                                        default=str,
                                    ).encode()
                                ).hexdigest(),
                                "observed_graph_sha256": hashlib.sha256(
                                    json.dumps(
                                        replayed_graph_state.get("graphs"),
                                        sort_keys=True,
                                        default=str,
                                    ).encode()
                                ).hexdigest(),
                                "expected_raw_exports": graph_state.get("raw_exports"),
                                "observed_raw_exports": replayed_graph_state.get(
                                    "raw_exports"
                                ),
                            },
                        )
                    rebound_target = _persist_target_graph_before_checkpoint(
                        conn, rebound_target, replayed_graph_state
                    )
                version_ops.prune_checkpoints_exact(
                    checkpoint_session,
                    [str(checkpoint["id"])],
                    project_name=str(checkpoint["project_name"]),
                    timeline_id=str(checkpoint["timeline_id"]),
                )
                if primary_error is None:
                    # Private handoff consumed by RenderMutationProof.capture; never
                    # include a scripting proxy in the public JSON proof envelope.
                    evidence_rebound_target = rebound_target
            except Exception as exc:
                cleanup_errors.append(
                    {
                        "phase": "restore_checkpoint_render_custody",
                        "error": str(exc),
                        "details": dict(getattr(exc, "details", {}) or {}),
                    }
                )
        if cleanup_errors:
            raise APICallFailed(
                "Authoritative rendered effect proof could not restore the user's Deliver context.",
                details={
                    "cleanup_errors": cleanup_errors,
                    "original_error": str(primary_error) if primary_error else None,
                },
                recoverability="manual",
            ) from primary_error
    if evidence is None:
        raise APICallFailed(
            "Authoritative one-frame Deliver proof produced no evidence."
        )
    if checkpoint is not None:
        if evidence_rebound_target is None:
            raise APICallFailed(
                "Exact render target was not rebound after checkpoint restore."
            )
        evidence["_rebound_target"] = evidence_rebound_target
    return evidence


def _rgb(path: Path):
    import numpy as np

    result = subprocess.run(
        [
            resolve_tool("ffmpeg"),
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            f"scale={_WIDTH}:{_HEIGHT}",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        capture_output=True,
        timeout=30,
        check=False,
    )
    expected = _WIDTH * _HEIGHT * 3
    if result.returncode != 0 or len(result.stdout) < expected:
        raise APICallFailed(
            "Failed to decode rendered mutation evidence.",
            details={
                "path": str(path),
                "returncode": result.returncode,
                "stderr": result.stderr[-500:].decode(errors="replace"),
            },
        )
    return (
        np.frombuffer(result.stdout[:expected], dtype=np.uint8)
        .reshape(_HEIGHT, _WIDTH, 3)
        .astype(np.int16)
    )


def compare_frames(before: Path, after: Path) -> dict[str, Any]:
    import numpy as np

    delta = np.abs(_rgb(before) - _rgb(after))
    changed_fraction = float(np.any(delta >= 2, axis=2).mean())
    mean_absolute_delta = float(delta.mean())
    changed = changed_fraction >= 0.001 and mean_absolute_delta >= 0.01
    return {
        "changed": changed,
        "changed_pixel_fraction": round(changed_fraction, 6),
        "mean_absolute_delta": round(mean_absolute_delta, 6),
        "sample_dimensions": {"width": _WIDTH, "height": _HEIGHT},
    }


class RenderMutationProof:
    """Retained rendered proof at the midpoint of one exact timeline item."""

    def __init__(
        self, conn: Any, target: TimelineItemTarget, proof_dir: str | None = None
    ):
        self.conn = conn
        self.target = target
        if proof_dir:
            base = Path(proof_dir).expanduser()
            base.mkdir(parents=True, exist_ok=True)
            self.directory = Path(
                tempfile.mkdtemp(prefix="cutagent-mutation-proof-", dir=base)
            )
        else:
            self.directory = Path(tempfile.mkdtemp(prefix="cutagent-mutation-proof-"))
        self.original_playhead = timeline_ops.get_playhead(conn)
        if target.start is None or target.end is None or target.end <= target.start:
            raise APICallFailed(
                "Exact target has no valid record range for rendered proof.",
                details={"target": target.public()},
            )
        self.proof_frame = target.start + max(0, (target.end - target.start - 1) // 2)

    def _position(self) -> dict[str, Any]:
        revalidate_timeline_item_target(self.conn, self.target)
        absolute_timecode = seconds_to_timecode(
            self.proof_frame / self.conn.fps, self.conn.fps
        )
        return timeline_ops.set_playhead(
            self.conn, absolute_timecode, return_details=True, frame_tolerance=0
        )

    def capture(self, label: str) -> dict[str, Any]:
        playhead = self._position()
        output_dir = self.directory / "deliver" / label
        output_dir.mkdir(parents=True, exist_ok=True)
        exported = _capture_deliver_frame(
            self.conn,
            output_dir,
            f"{label}_{self.proof_frame}",
            self.proof_frame,
            target=self.target,
        )
        self.target = exported.pop("_rebound_target")
        return {
            **exported,
            "label": label,
            "record_frame": self.proof_frame,
            "playhead": playhead,
        }

    def compare(self, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        return compare_frames(Path(before["path"]), Path(after["path"]))

    def restore_playhead(self) -> dict[str, Any] | None:
        timecode = (
            self.original_playhead.get("timecode")
            if isinstance(self.original_playhead, dict)
            else None
        )
        if not timecode:
            return None
        return timeline_ops.set_playhead(self.conn, str(timecode), return_details=True)
