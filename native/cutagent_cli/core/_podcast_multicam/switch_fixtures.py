"""Native multicam switch fixture loading and angle-index helpers."""

from __future__ import annotations

import base64
from importlib import resources
import json
import sqlite3
from typing import Any

from ...errors import APICallFailed, ValidationError
from .. import multicam_switch_families


def _decode_optional_blob_b64(value: Any) -> bytes:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(
            "Native multicam switch fixture is invalid.",
            details={"reason": "missing_fields_blob"},
        )
    try:
        return base64.b64decode(value)
    except Exception as exc:  # pragma: no cover - defensive
        raise ValidationError(
            "Native multicam switch fixture could not be decoded.",
            details={"reason": "invalid_base64"},
        ) from exc


def load_reference_multicam_switch_fixture(angle_count: int | None = None, *, ops_module):
    resolved_angle_count = max(2, int(angle_count or 2))
    fixture_name = ops_module._SWITCH_FIXTURE_NAME_BY_ANGLE_COUNT.get(
        resolved_angle_count,
        ops_module._SWITCH_FIXTURE_NAME_BY_ANGLE_COUNT[4]
        if resolved_angle_count >= 4
        else ops_module._SWITCH_FIXTURE_NAME_BY_ANGLE_COUNT[2],
    )
    try:
        fixture_text = resources.files(ops_module._SWITCH_FIXTURE_PACKAGE).joinpath(fixture_name).read_text(
            encoding="utf-8"
        )
    except Exception as exc:  # pragma: no cover - packaging/runtime failure
        raise ValidationError(
            "Native multicam switch fixture is missing.",
            details={"fixture": fixture_name},
        ) from exc

    try:
        payload = json.loads(fixture_text)
    except json.JSONDecodeError as exc:  # pragma: no cover - malformed fixture
        raise ValidationError(
            "Native multicam switch fixture is not valid JSON.",
            details={"fixture": fixture_name, "error": str(exc)},
        ) from exc

    if not isinstance(payload, dict):
        raise ValidationError(
            "Native multicam switch fixture is invalid.",
            details={"fixture": fixture_name},
        )

    def _parse_templates(raw_items: Any) -> list[Any]:
        templates: list[Any] = []
        for raw in list(raw_items or []):
            if not isinstance(raw, dict):
                continue
            angle_index = raw.get("angle_index")
            templates.append(
                ops_module.NativeSwitchSegmentTemplate(
                    position=str(raw.get("position") or "middle").strip() or "middle",
                    angle_index=int(angle_index) if angle_index not in (None, "") else None,
                    start=str(raw.get("start") or "0"),
                    duration=str(raw.get("duration") or "0"),
                    in_value=str(raw.get("in_value")).strip() if raw.get("in_value") not in (None, "") else None,
                    current_selector_idx=int(raw.get("current_selector_idx") or 0),
                    fields_blob=_decode_optional_blob_b64(raw.get("fields_blob_b64")),
                    media_timemap_ba=(
                        _decode_optional_blob_b64(raw.get("media_timemap_b64"))
                        if raw.get("media_timemap_b64") not in (None, "")
                        else None
                    ),
                    effect_filters_ba=(
                        _decode_optional_blob_b64(raw.get("effect_filters_b64"))
                        if raw.get("effect_filters_b64") not in (None, "")
                        else None
                    ),
                )
            )
        return templates

    video_segments = _parse_templates(payload.get("video_segments"))
    audio_segments = _parse_templates(payload.get("audio_segments"))
    if not video_segments or not audio_segments:
        raise ValidationError(
            "Native multicam switch fixture is incomplete.",
            details={"fixture": fixture_name},
        )

    return ops_module.NativeSwitchReferenceFixture(
        schema_family=str(payload.get("schema_family") or "resolve_20x"),
        fixture_version=int(payload.get("fixture_version") or 1),
        angle_count=resolved_angle_count,
        video_segments=video_segments,
        audio_segments=audio_segments,
    )


def _load_matching_project_multicam_switch_fixture(
    project_db_path: str,
    *,
    multicam_name: str,
    angle_count: int,
    ops_module,
):
    if int(angle_count) < 3:
        return None

    canonical_fixture = load_reference_multicam_switch_fixture(angle_count=angle_count, ops_module=ops_module)
    expected_video_count = int(angle_count) if int(angle_count) >= 5 else len(canonical_fixture.video_segments)
    expected_audio_count = int(angle_count) if int(angle_count) >= 5 else len(canonical_fixture.audio_segments)

    connection = sqlite3.connect(project_db_path)
    try:
        connection.row_factory = sqlite3.Row
        candidate_rows = connection.execute(
            """
            SELECT
                item.Name AS ClipName,
                SUM(CASE WHEN item.DbType = 'Sm2TiVideoClip' THEN 1 ELSE 0 END) AS VideoCount,
                SUM(CASE WHEN item.DbType = 'Sm2TiAudioClip' THEN 1 ELSE 0 END) AS AudioCount,
                MAX(CAST(item.Start AS INTEGER)) AS MaxStart
            FROM Sm2TiItem item
            JOIN Sm2MpMedia media ON media.Name = item.Name
            WHERE item.Name != ?
            GROUP BY item.Name
            HAVING VideoCount = ? AND AudioCount = ?
            ORDER BY MaxStart DESC, ClipName DESC
            """,
            (multicam_name, expected_video_count, expected_audio_count),
        ).fetchall()

        def _candidate_sort_key(row: sqlite3.Row) -> tuple[int, int, int, str]:
            clip_name = str(row["ClipName"] or "").strip()
            preferred = int(clip_name not in ops_module._PREFERRED_LOCAL_MULTICAM_SWITCH_REFERENCE_NAMES)
            generated = int(clip_name.startswith(ops_module._TOOL_GENERATED_MULTICAM_NAME_PREFIXES))
            max_start = int(row["MaxStart"] or 0)
            return (preferred, generated, -max_start, clip_name.lower())

        for candidate in sorted(candidate_rows, key=_candidate_sort_key):
            clip_name = str(candidate["ClipName"] or "").strip()
            if not clip_name:
                continue
            if int(angle_count) == 4 and clip_name not in ops_module._PREFERRED_LOCAL_MULTICAM_SWITCH_REFERENCE_NAMES:
                continue

            video_rows = connection.execute(
                """
                SELECT Start, Duration, "In" AS InValue, CurrentSelectorIdx, FieldsBlob
                     , MediaTimemapBA, EffectFiltersBA
                FROM Sm2TiItem
                WHERE Name = ? AND DbType = 'Sm2TiVideoClip'
                ORDER BY CAST(Start AS INTEGER), rowid
                """,
                (clip_name,),
            ).fetchall()
            audio_rows = connection.execute(
                """
                SELECT Start, Duration, "In" AS InValue, CurrentSelectorIdx, FieldsBlob
                     , MediaTimemapBA, EffectFiltersBA
                FROM Sm2TiItem
                WHERE Name = ? AND DbType = 'Sm2TiAudioClip'
                ORDER BY CAST(Start AS INTEGER), rowid
                """,
                (clip_name,),
            ).fetchall()
            if len(video_rows) != expected_video_count or len(audio_rows) != expected_audio_count:
                continue

            def _local_template_position(index: int, track_type: str) -> str:
                templates = canonical_fixture.video_segments if track_type == "video" else canonical_fixture.audio_segments
                if int(angle_count) < 5 and index < len(templates):
                    return templates[index].position
                total_segments = expected_video_count if track_type == "video" else expected_audio_count
                return ops_module._segment_template_position(index, total_segments)

            def _local_template_angle_index(index: int, track_type: str) -> int | None:
                templates = canonical_fixture.video_segments if track_type == "video" else canonical_fixture.audio_segments
                if int(angle_count) < 5 and index < len(templates):
                    return templates[index].angle_index
                return index

            video_segments = [
                ops_module.NativeSwitchSegmentTemplate(
                    position=_local_template_position(index, "video"),
                    angle_index=_local_template_angle_index(index, "video"),
                    start=str(row["Start"] or "0"),
                    duration=str(row["Duration"] or "0"),
                    in_value=str(row["InValue"]).strip() if row["InValue"] not in (None, "") else None,
                    current_selector_idx=int(row["CurrentSelectorIdx"] or 0),
                    fields_blob=bytes(row["FieldsBlob"] or b""),
                    media_timemap_ba=bytes(row["MediaTimemapBA"] or b"") if row["MediaTimemapBA"] is not None else None,
                    effect_filters_ba=bytes(row["EffectFiltersBA"] or b"") if row["EffectFiltersBA"] is not None else None,
                )
                for index, row in enumerate(video_rows)
            ]
            audio_segments = [
                ops_module.NativeSwitchSegmentTemplate(
                    position=_local_template_position(index, "audio"),
                    angle_index=_local_template_angle_index(index, "audio"),
                    start=str(row["Start"] or "0"),
                    duration=str(row["Duration"] or "0"),
                    in_value=str(row["InValue"]).strip() if row["InValue"] not in (None, "") else None,
                    current_selector_idx=int(row["CurrentSelectorIdx"] or 0),
                    fields_blob=bytes(row["FieldsBlob"] or b""),
                    media_timemap_ba=bytes(row["MediaTimemapBA"] or b"") if row["MediaTimemapBA"] is not None else None,
                    effect_filters_ba=bytes(row["EffectFiltersBA"] or b"") if row["EffectFiltersBA"] is not None else None,
                )
                for index, row in enumerate(audio_rows)
            ]
            return ops_module.NativeSwitchReferenceFixture(
                schema_family="project_local_resolve_20x",
                fixture_version=canonical_fixture.fixture_version,
                angle_count=int(angle_count),
                video_segments=video_segments,
                audio_segments=audio_segments,
            )
    finally:
        connection.close()

    return None


def _resolve_multicam_angle_indices(
    project_db_path: str,
    *,
    multicam_name: str,
    expected_clip_names: list[str] | None = None,
    multicam_media_id: str | None = None,
) -> dict[str, int]:
    connection = sqlite3.connect(project_db_path)
    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                rel.DbIndex AS AngleIndex,
                source.Name AS SourceClipName
            FROM Sm2MpMedia multicam
            JOIN Sm2Sequence seq ON seq.Sm2MpMedia_id = multicam.Sm2MpMedia_id
            JOIN Sm2SequenceContainer container ON container.Sm2Sequence_id = seq.Sm2Sequence_id
            JOIN Sm2SequenceContainer_Sm2TiTrack rel
              ON rel.DbOwner = container.Sm2SequenceContainer_id
             AND rel.DbPropertyName = 'VideoTrackVec'
            JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel.DbAssociate
            LEFT JOIN Sm2TiItem item
              ON item.Sm2TiTrack_id = track.Sm2TiTrack_id
             AND item.DbType = 'Sm2TiVideoClip'
            LEFT JOIN Sm2MpMedia source ON source.Sm2MpMedia_id = item.MediaRef
            WHERE multicam.Name = ?
              AND (? IS NULL OR multicam.Sm2MpMedia_id = ?)
            ORDER BY rel.DbIndex
            """,
            (multicam_name, multicam_media_id, multicam_media_id),
        ).fetchall()
    finally:
        connection.close()

    mapping = {
        str(row["SourceClipName"] or "").strip(): int(row["AngleIndex"] or 0)
        for row in rows
        if str(row["SourceClipName"] or "").strip()
    }
    if expected_clip_names:
        ordered_expected: list[str] = []
        for clip_name in expected_clip_names:
            normalized = str(clip_name or "").strip()
            if normalized and normalized not in ordered_expected:
                ordered_expected.append(normalized)
        remaining_expected = [clip_name for clip_name in ordered_expected if clip_name not in mapping]
        for row in rows:
            source_name = str(row["SourceClipName"] or "").strip()
            if source_name:
                continue
            if not remaining_expected:
                break
            mapping[remaining_expected.pop(0)] = int(row["AngleIndex"] or 0)
    if not mapping:
        raise APICallFailed(
            "Could not resolve multicam angle ordering from Project.db.",
            details={"multicam_name": multicam_name, "project_db_path": project_db_path},
        )
    return mapping


def _segment_template_position(index: int, total_segments: int) -> str:
    if index <= 0:
        return "first"
    if index >= max(0, total_segments - 1):
        return "last"
    return "middle"


def _select_native_switch_template(
    templates: list[Any],
    *,
    position: str,
    angle_index: int | None,
):
    exact = [
        template
        for template in templates
        if template.position == position and template.angle_index == angle_index
    ]
    if exact:
        return exact[0]

    same_angle = [template for template in templates if template.angle_index == angle_index]
    if same_angle:
        if position != "first":
            non_initial = [template for template in same_angle if template.position in {"middle", "last"}]
            if non_initial:
                return non_initial[0]
        return same_angle[0]

    same_position = [template for template in templates if template.position == position]
    if same_position:
        return same_position[0]

    if position != "first":
        continuing = [template for template in templates if template.position in {"middle", "last"}]
        if continuing:
            return continuing[0]

    return templates[0]


def _resolve_switch_template_angle_index(*, segment, local_angle_index: int, angle_count: int) -> int:
    return multicam_switch_families.resolve_template_angle_index(
        angle_count=angle_count,
        segment_angle=segment.angle,
        local_angle_index=local_angle_index,
    )
