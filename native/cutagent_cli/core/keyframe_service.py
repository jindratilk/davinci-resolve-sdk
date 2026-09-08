"""Typed native service shared by clip-keyframe CLI and prepared SDK paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, TypedDict

from ..errors import ValidationError
from . import keyframe_ops


class KeyframeRow(TypedDict, total=False):
    index: int
    frame: int
    local_frame: int
    value: float
    db_value: float
    interpolation: str
    interpolation_code: int
    interpolation_flags: int


class KeyframeMutationDetail(TypedDict, total=False):
    frame: int
    local_frame: int
    value: float
    interpolation: str
    interpolation_code: int
    interpolation_flags: int


class KeyframeVerification(TypedDict, total=False):
    status: str
    readback_count: int
    keyframes: list[KeyframeRow]


class KeyframeOperationResult(TypedDict, total=False):
    clip: str | None
    item_id: str
    property: str | None
    count: int
    keyframes: list[KeyframeRow] | dict[str, list[KeyframeRow]]
    route: str
    db_session_route: str
    verification: KeyframeVerification
    steps: list[str]
    added: KeyframeMutationDetail
    deleted: KeyframeMutationDetail
    updated: KeyframeMutationDetail


@dataclass(frozen=True)
class AddKeyframe:
    clip_name: str | None
    property_name: str
    record_frame: int
    value: float
    interpolation: str | int | None = None


@dataclass(frozen=True)
class GetKeyframes:
    clip_name: str | None
    property_name: str | None = None


@dataclass(frozen=True)
class DeleteKeyframe:
    clip_name: str | None
    property_name: str
    record_frame: int


@dataclass(frozen=True)
class SetKeyframeInterpolation:
    clip_name: str | None
    property_name: str
    record_frame: int
    interpolation: str


KeyframeRequest = AddKeyframe | GetKeyframes | DeleteKeyframe | SetKeyframeInterpolation


class KeyframeBackend(Protocol):
    def add_keyframe(self, conn: Any, clip_name: str | None, property_name: str,
                     frame: int, value: float, interpolation: str | int | None = None) -> Mapping[str, Any]: ...

    def get_keyframes(self, conn: Any, clip_name: str | None,
                      property_name: str | None = None) -> Mapping[str, Any]: ...

    def delete_keyframe(self, conn: Any, clip_name: str | None,
                        property_name: str, frame: int) -> Mapping[str, Any]: ...

    def set_keyframe_interpolation(self, conn: Any, clip_name: str | None,
                                   property_name: str, frame: int,
                                   interpolation_type: str) -> Mapping[str, Any]: ...


def execute_keyframe(
    conn: Any,
    request: KeyframeRequest,
    *,
    backend: KeyframeBackend = keyframe_ops,
) -> KeyframeOperationResult:
    """Execute one already-admitted keyframe request through the native owner."""

    if isinstance(request, AddKeyframe):
        args = (
            conn, request.clip_name, request.property_name,
            request.record_frame, request.value,
        )
        if request.interpolation is None:
            result = backend.add_keyframe(*args)
        else:
            result = backend.add_keyframe(*args, request.interpolation)
    elif isinstance(request, GetKeyframes):
        result = backend.get_keyframes(conn, request.clip_name, request.property_name)
    elif isinstance(request, DeleteKeyframe):
        result = backend.delete_keyframe(
            conn, request.clip_name, request.property_name, request.record_frame
        )
    elif isinstance(request, SetKeyframeInterpolation):
        result = backend.set_keyframe_interpolation(
            conn,
            request.clip_name,
            request.property_name,
            request.record_frame,
            request.interpolation,
        )
    else:
        raise TypeError("Unsupported typed keyframe request.")

    if not isinstance(result, Mapping):
        raise ValidationError("Keyframe native service returned no structured result.")
    return dict(result)
