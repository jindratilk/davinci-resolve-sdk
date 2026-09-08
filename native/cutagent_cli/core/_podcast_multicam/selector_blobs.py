from __future__ import annotations

import struct

from ...errors import ValidationError
from .. import multicam_switch_families


def _build_compact_angle_selector_fields_blob(local_angle_index: int) -> bytes:
    return multicam_switch_families.build_compact_angle_selector_fields_blob(local_angle_index)


def _build_two_cam_camera_selector_fields_blob(*, local_angle_index: int, track_type: str) -> bytes:
    display_index = max(1, int(local_angle_index) + 1)
    label = f"Camera {display_index}".encode("utf-8")
    if track_type == "audio":
        payload = (
            b"\x80\x0A\x11\x0A\x03\xA8\x01\x00\x1A"
            + bytes([len(label)])
            + label
            + b"\x20\x01\x78\x04"
        )
    else:
        payload = (
            b"\x80\x0A\x11\x0A\x03\xA8\x01\x00\x1A"
            + bytes([len(label)])
            + label
            + b"\x20\x01\x12\x10\x00\x00\x00\x00\x00\x00\x00\x05\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF"
        )
    return struct.pack(">I", display_index) + struct.pack(">I", len(payload)) + payload


_THREE_CAM_WHOLE_CLIP_SELECTOR_FIELDS_BLOBS: dict[tuple[int, str], bytes] = {
    (0, "video"): bytes.fromhex("000000020000006E8128B52FFD2083250300C2461520B027AD010CC3300CC304B445AD65C5A680066B0951B7C65E5EC2402B6168240577777777810342A2348A45A2872D040543A7F350652A9AEB52D7C4A5855AC46594B93E97AB7574429FAACAF874262079235982A40400E0C6F53C8D2D0DEE3A24"),
    (1, "video"): bytes.fromhex("000000020000006E8128B52FFD2083250300C2461520B027AD010CC3300CC304B445AD65C5A680066B09516B825F5EC2402B6168240577777777810342A2348A45A2872D0485A6D379A8321586EB52D7C4A5855AC46594B93E97AB7574429FAACAF874262079235982A40400E0C6F53C8D2D0DEE3A24"),
    (0, "audio"): bytes.fromhex("000000020000005C8128B52FFD2073950200C28612179029E7BB66D80E8AE6E318A0B5720B73D0AB416711B51481C6812448633C45330806894B564D93ADBB2454A2E7BAA2ECA926BAEBA94C0BDDF375D3775555F6F0E628E038C234B330010100670E09"),
    (1, "audio"): bytes.fromhex("000000020000005B8128B52FFD20738D0200C24612179029E7BB66E0E514CDC731406BE54A71D0AB416711B51481C68124A4319EA21D0483A5925553C2D6551626D1735D51F65497EE7A265343F77CDDF45D559545BC390A389E30CD2C4C0100670E09"),
    (2, "video"): bytes.fromhex("0000000200000021800A0C1A0843616D6572612033200112100000000000000005FFFFFFFFFFFFFFFF"),
    (2, "audio"): bytes.fromhex("0000000200000011800A0C1A0843616D657261203320017804"),
}


def _build_three_cam_whole_clip_selector_fields_blob(*, local_angle_index: int, track_type: str) -> bytes:
    key = (int(local_angle_index), str(track_type))
    blob = _THREE_CAM_WHOLE_CLIP_SELECTOR_FIELDS_BLOBS.get(key)
    if blob is None:
        raise ValidationError(
            "Native 3-cam whole-clip switch is not yet calibrated for this angle.",
            details={
                "step": "three_cam_whole_clip_angle_not_calibrated",
                "local_angle_index": int(local_angle_index),
                "track_type": str(track_type),
                "supported_angle_indices": sorted(
                    angle_index
                    for angle_index, blob_track_type in _THREE_CAM_WHOLE_CLIP_SELECTOR_FIELDS_BLOBS.keys()
                    if blob_track_type == str(track_type)
                ),
            },
        )
    return blob


def _patch_three_angle_selector_fields_blob(
    template_blob: bytes,
    *,
    position: str,
    template_angle_index: int,
    track_type: str,
) -> bytes:
    return multicam_switch_families.patch_three_angle_selector_fields_blob(
        template_blob,
        position=position,
        template_angle_index=template_angle_index,
        track_type=track_type,
    )


def _build_switch_fields_blob(
    *,
    template,
    segment,
    local_angle_index: int,
    template_angle_index: int,
    segment_index: int,
    total_segments: int,
    angle_count: int,
    track_type: str,
    calibrated_project_local_reference: bool = False,
) -> bytes:
    _ = calibrated_project_local_reference
    if int(angle_count) == 2 and int(total_segments) > 1 and int(segment_index) > 0:
        return _build_two_cam_camera_selector_fields_blob(
            local_angle_index=local_angle_index,
            track_type=track_type,
        )
    if int(angle_count) == 3 and int(total_segments) > 1 and int(local_angle_index) == 2:
        return _build_three_cam_whole_clip_selector_fields_blob(
            local_angle_index=local_angle_index,
            track_type=track_type,
        )
    if int(angle_count) >= 5:
        return bytes(template.fields_blob)
    return multicam_switch_families.build_switch_fields_blob(
        template=template,
        segment_angle=segment.angle,
        local_angle_index=local_angle_index,
        template_angle_index=template_angle_index,
        angle_count=angle_count,
        track_type=track_type,
    )
