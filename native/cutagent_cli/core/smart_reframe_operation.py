"""Truthful long-running operation wrapper for TimelineItem.SmartReframe."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from ..errors import APICallFailed, CLIError, SmartReframeVerificationFailed
from ..output import set_recoverability, set_verification_status
from ..policy import require_api_method
from .effect_render_proof import RenderMutationProof
from .mutation_target import resolve_timeline_item_target, revalidate_timeline_item_target


def _write_progress(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _try_write_progress(path: Path | None, payload: dict[str, Any]) -> bool:
    try:
        _write_progress(path, payload)
        return True
    except Exception as exc:
        payload["progress_journal"] = {"status": "failed", "error": str(exc)}
        return False


def _cancel_requested(path: Path | None) -> bool:
    return bool(path and path.is_file())


def _restore_playhead(proof: RenderMutationProof) -> dict[str, Any] | None:
    try:
        return {"ok": True, "readback": proof.restore_playhead()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _terminal_render_evidence(
    proof: RenderMutationProof,
    before: dict[str, Any],
    after: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {"before": before, "directory": str(proof.directory)}
    try:
        terminal = after or proof.capture("terminal_failure")
        evidence["after"] = terminal
        evidence["comparison"] = proof.compare(before, terminal)
    except Exception as exc:
        evidence["terminal_capture_error"] = str(exc)
    return evidence


def run_smart_reframe(
    conn: Any,
    *,
    clip_name: str | None = None,
    item_id: str | None = None,
    track: int | None = None,
    record_frame: str | int | None = None,
    operation_id: str | None = None,
    progress_file: str | None = None,
    cancel_request_file: str | None = None,
    proof_dir: str | None = None,
    poll_ms: int = 250,
) -> dict[str, Any]:
    """Run the synchronous native call while exposing honest phase/cancel state."""
    op_id = str(operation_id or uuid.uuid4())
    progress_path = Path(progress_file).expanduser() if progress_file else None
    cancel_path = Path(cancel_request_file).expanduser() if cancel_request_file else None
    target = resolve_timeline_item_target(conn, clip_name, item_id=item_id, track=track, record_frame=record_frame)
    operation: dict[str, Any] = {
        "id": op_id,
        "kind": "clip.smart_reframe",
        "status": "running",
        "phase": "preflight",
        "target": target.public(),
        "progress": {"mode": "phase_only", "native_fraction_available": False},
        "cancellation": {
            "supported_by_native_api": False,
            "requested": False,
            "confirmed": False,
        },
        "started_at_unix_ms": int(time.time() * 1000),
    }
    _write_progress(progress_path, operation)
    if _cancel_requested(cancel_path):
        operation.update({"status": "cancelled", "phase": "terminal", "finished_at_unix_ms": int(time.time() * 1000)})
        operation["cancellation"].update({"requested": True, "confirmed": True, "confirmation_scope": "before_native_mutation"})
        _try_write_progress(progress_path, operation)
        return {"operation": operation, "verification": {"status": "not_run", "reason": "cancelled_before_native_mutation"}}

    proof = None
    try:
        proof = RenderMutationProof(conn, target, proof_dir)
        before = proof.capture("before")
        target = proof.target
        target = revalidate_timeline_item_target(conn, target)
        method = require_api_method(target.item, "SmartReframe", capability_id="clip.smart_reframe", runtime_object="timeline_item")
        operation["phase"] = "native_call"
        _write_progress(progress_path, operation)
    except BaseException as exc:
        if proof is not None:
            operation["playhead_restore"] = _restore_playhead(proof)
        operation.update({"status": "failed", "phase": "terminal", "finished_at_unix_ms": int(time.time() * 1000)})
        operation["error"] = {"code": getattr(exc, "code", "INTERNAL_ERROR"), "message": str(exc)}
        _try_write_progress(progress_path, operation)
        raise
    if _cancel_requested(cancel_path):
        operation["playhead_restore"] = _restore_playhead(proof)
        operation.update({"status": "cancelled", "phase": "terminal", "finished_at_unix_ms": int(time.time() * 1000)})
        operation["cancellation"].update({"requested": True, "confirmed": True, "confirmation_scope": "before_native_mutation"})
        _try_write_progress(progress_path, operation)
        return {"operation": operation, "verification": {"status": "not_run", "reason": "cancelled_before_native_mutation"}}
    result_box: dict[str, Any] = {}

    def invoke() -> None:
        try:
            result_box["result"] = method()
        except BaseException as exc:  # preserve native exception for the caller thread
            result_box["exception"] = exc

    worker = threading.Thread(target=invoke, name=f"smart-reframe-{op_id}", daemon=False)
    worker.start()
    try:
        while worker.is_alive():
            worker.join(max(0.05, min(5.0, int(poll_ms) / 1000.0)))
            if _cancel_requested(cancel_path) and not operation["cancellation"]["requested"]:
                operation["cancellation"].update(
                    {
                        "requested": True,
                        "confirmed": False,
                        "reason": "TimelineItem.SmartReframe exposes no native cancellation API; waiting for terminal result.",
                    }
                )
                _try_write_progress(progress_path, operation)
    except KeyboardInterrupt:
        operation["cancellation"].update(
            {
                "requested": True,
                "confirmed": False,
                "reason": "Interrupt recorded, but the native call cannot be abandoned while mutation may continue.",
            }
        )
        _try_write_progress(progress_path, operation)
        while worker.is_alive():
            try:
                worker.join(0.25)
            except KeyboardInterrupt:
                continue
    if _cancel_requested(cancel_path) and not operation["cancellation"]["requested"]:
        operation["cancellation"].update(
            {
                "requested": True,
                "confirmed": False,
                "reason": "Cancellation timing overlapped or followed the non-cancellable native call.",
            }
        )
        _try_write_progress(progress_path, operation)

    after: dict[str, Any] | None = None
    try:
        if "exception" in result_box:
            native_exc = result_box["exception"]
            raise APICallFailed(
                "TimelineItem.SmartReframe raised during native execution.",
                details={"native_error": str(native_exc), "target": target.public(), "capability_status": "partial"},
                recoverability="manual",
            ) from native_exc
        if not bool(result_box.get("result")):
            raise APICallFailed(
                "Smart Reframe failed in the active DaVinci Resolve edition or timeline.",
                details={"target": target.public(), "capability_status": "partial"},
                recoverability="manual",
                suggested_fix="Use DaVinci Resolve Studio with a timeline whose aspect ratio differs from the source, or reframe the clip manually.",
            )
        operation["phase"] = "verification"
        _try_write_progress(progress_path, operation)
        after = proof.capture("after")
        target = proof.target
        comparison = proof.compare(before, after)
        if not comparison["changed"]:
            raise SmartReframeVerificationFailed(
                "Smart Reframe returned without a render-visible framing change.",
            )
    except BaseException as exc:
        failure = exc if isinstance(exc, CLIError) else APICallFailed(
            "Smart Reframe failed after native execution began.",
            details={"native_error": str(exc)},
            recoverability="manual",
        )
        evidence = _terminal_render_evidence(proof, before, after)
        target = proof.target
        operation["playhead_restore"] = _restore_playhead(proof)
        failure.details.update(
            {
                "target": target.public(),
                "possible_mutation": True,
                "rollback": {"available": False, "reason": "TimelineItem.SmartReframe exposes no native inverse operation."},
                "render_proof": evidence,
                "playhead_restore": operation["playhead_restore"],
            }
        )
        operation.update({"status": "failed", "phase": "terminal", "finished_at_unix_ms": int(time.time() * 1000)})
        operation["error"] = {"code": failure.code, "message": str(failure), "details": failure.details}
        _try_write_progress(progress_path, operation)
        if failure is exc:
            raise failure
        raise failure from exc

    restored = _restore_playhead(proof)
    if restored and not restored["ok"]:
        failure_details = {
            "target": target.public(),
            "playhead_restore": restored,
            "possible_mutation": True,
            "rollback": {"available": False, "reason": "TimelineItem.SmartReframe exposes no native inverse operation."},
            "render_proof": {
                "before": before,
                "after": after,
                "comparison": comparison,
                "directory": str(proof.directory),
            },
        }
        operation.update({"status": "failed", "phase": "terminal", "finished_at_unix_ms": int(time.time() * 1000)})
        operation["error"] = {
            "code": "SMART_REFRAME_VERIFICATION_FAILED",
            "message": "Smart Reframe completed, but the original playhead could not be restored.",
            "details": failure_details,
        }
        operation["playhead_restore"] = restored
        _try_write_progress(progress_path, operation)
        set_verification_status("failed")
        raise SmartReframeVerificationFailed(
            operation["error"]["message"],
            details=failure_details,
        )
    operation.update({"status": "succeeded", "phase": "terminal", "finished_at_unix_ms": int(time.time() * 1000)})
    if operation["cancellation"]["requested"]:
        operation["cancellation"]["confirmed"] = False
        operation["cancellation"]["terminal_note"] = "The native mutation completed; cancellation was requested but not confirmed."
    _try_write_progress(progress_path, operation)
    set_verification_status("verified")
    set_recoverability("not_applicable")
    return {
        "operation": operation,
        "verification": {
            "status": "verified",
            "checks": [{"name": "native_terminal_result", "ok": True}, {"name": "rendered_framing_change", "ok": True, **comparison}],
            "render_proof": {"before": before, "after": after, "directory": str(proof.directory), "restored_playhead": restored},
        },
        "rollback": {"available": False, "reason": "TimelineItem.SmartReframe exposes no native inverse operation."},
    }
