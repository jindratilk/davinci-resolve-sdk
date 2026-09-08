_SOCIAL_CROP_PRESETS: dict[str, tuple[int, int, str]] = {
    "vertical": (1080, 1920, "9:16"),
    "9:16": (1080, 1920, "9:16"),
    "reels": (1080, 1920, "9:16"),
    "tiktok": (1080, 1920, "9:16"),
    "shorts": (1080, 1920, "9:16"),
    "square": (1080, 1080, "1:1"),
    "1:1": (1080, 1080, "1:1"),
    "portrait": (1080, 1350, "4:5"),
    "4:5": (1080, 1350, "4:5"),
    "landscape": (1920, 1080, "16:9"),
    "16:9": (1920, 1080, "16:9"),
}


def _parse_social_aspect(value: str) -> float:
    text = str(value or "").strip().lower()
    if text in _SOCIAL_CROP_PRESETS:
        width, height, _ = _SOCIAL_CROP_PRESETS[text]
        return width / height
    if ":" in text:
        left, _, right = text.partition(":")
        try:
            width = float(left)
            height = float(right)
        except ValueError as exc:
            raise ValidationError("Aspect ratio must be WIDTH:HEIGHT.", details={"aspect": value}) from exc
        if width <= 0 or height <= 0:
            raise ValidationError("Aspect ratio values must be greater than 0.", details={"aspect": value})
        return width / height
    try:
        numeric = float(text)
    except ValueError as exc:
        raise ValidationError("Aspect ratio must be WIDTH:HEIGHT or a positive number.", details={"aspect": value}) from exc
    if numeric <= 0:
        raise ValidationError("Aspect ratio must be greater than 0.", details={"aspect": value})
    return numeric


def _resolve_social_crop_preset(format_name: str) -> tuple[int, int, str]:
    key = str(format_name or "").strip().lower()
    preset = _SOCIAL_CROP_PRESETS.get(key)
    if preset is None:
        raise ValidationError(
            "Unknown social crop format.",
            details={"format": format_name, "supported": sorted(_SOCIAL_CROP_PRESETS)},
        )
    return preset


def _social_crop_zoom(*, target_aspect: float, source_aspect: float, zoom: float | None) -> float:
    if zoom is not None:
        if zoom <= 0:
            raise ValidationError("Social crop zoom must be greater than 0.", details={"zoom": zoom})
        return float(zoom)
    if target_aspect <= 0 or source_aspect <= 0:
        raise ValidationError(
            "Social crop aspect ratios must be greater than 0.",
            details={"target_aspect": target_aspect, "source_aspect": source_aspect},
        )
    return round(max(target_aspect / source_aspect, source_aspect / target_aspect, 1.0), 4)


def _item_display_name(item, fallback: str) -> str:
    getter = getattr(item, "GetName", None)
    if callable(getter):
        try:
            name = str(getter() or "").strip()
            if name:
                return name
        except Exception:
            pass
    return fallback


def _set_social_crop_transform(item, *, zoom: float, pan: float, tilt: float) -> dict[str, object]:
    props = {"ZoomX": zoom, "ZoomY": zoom, "Pan": pan, "Tilt": tilt}
    failed: list[str] = []
    for key, value in props.items():
        setter = getattr(item, "SetProperty", None)
        if not callable(setter):
            failed.append(key)
            continue
        result = setter(key, value)
        if result is False:
            failed.append(key)
    if failed:
        raise APICallFailed("Failed to apply social crop transform.", details={"failed_properties": failed})
    return props


def _find_fusion_tool(comp: Any, reg_id: str) -> Any | None:
    try:
        tools = comp.GetToolList(False) or {}
    except Exception:
        return None
    for tool in tools.values():
        try:
            attrs = tool.GetAttrs() if hasattr(tool, "GetAttrs") else {}
            if attrs.get("TOOLS_RegID") == reg_id:
                return tool
        except Exception:
            continue
    return None


def _ensure_item_fusion_comp(item: Any, *, clip_name: str) -> Any:
    count = 0
    try:
        count = int(item.GetFusionCompCount() or 0)
    except Exception:
        count = 0
    if count <= 0:
        add_comp = getattr(item, "AddFusionComp", None)
        if not callable(add_comp):
            raise APICallFailed("Camera PiP rounded crop requires AddFusionComp support on the camera timeline item.")
        if add_comp() is False:
            raise APICallFailed("Failed to add Fusion composition for camera PiP rounded crop.", details={"clip": clip_name})
        try:
            count = int(item.GetFusionCompCount() or 1)
        except Exception:
            count = 1
    comp = item.GetFusionCompByIndex(1) if hasattr(item, "GetFusionCompByIndex") else None
    if not comp:
        raise APICallFailed("Could not access Fusion composition for camera PiP rounded crop.", details={"clip": clip_name})
    return comp


def _connect_mask_to_media_in(media_in: Any, mask: Any) -> str:
    output_port = None
    find_output = getattr(mask, "FindOutput", None)
    if callable(find_output):
        try:
            output_port = find_output("Output")
        except Exception:
            output_port = None

    for input_name in ("EffectMask", "Mask"):
        find_input = getattr(media_in, "FindInput", None)
        if callable(find_input) and output_port is not None:
            try:
                input_port = find_input(input_name)
                if input_port and input_port.ConnectTo(output_port) is not False:
                    return f"{input_name}.ConnectTo(Output)"
            except Exception:
                pass
        setter = getattr(media_in, "SetInput", None)
        if callable(setter):
            try:
                if setter(input_name, mask) is not False:
                    return f"{input_name}.SetInput(mask)"
            except Exception:
                pass
    raise APICallFailed(
        "Failed to connect camera PiP rounded crop mask to MediaIn.",
        details={"attempted_inputs": ["EffectMask", "Mask"]},
    )


def _apply_camera_pip_rounded_crop(item: Any, *, clip_name: str, radius: float, softness: float) -> dict[str, object]:
    if radius <= 0:
        return {"applied": False, "reason": "radius_disabled"}
    comp = _ensure_item_fusion_comp(item, clip_name=clip_name)
    add_tool = getattr(comp, "AddTool", None)
    if not callable(add_tool):
        raise APICallFailed("Fusion composition cannot create the camera PiP rounded crop mask.")
    mask = add_tool("RectangleMask", -32768, -32768)
    if not mask:
        raise APICallFailed("Failed to create RectangleMask for camera PiP rounded crop.")
    for key, value in (
        ("Center", {1: 0.5, 2: 0.5}),
        ("Width", 1.0),
        ("Height", 1.0),
        ("CornerRadius", float(radius)),
        ("SoftEdge", float(softness)),
    ):
        try:
            mask.SetInput(key, value)
        except Exception as exc:
            raise APICallFailed(
                "Failed to configure camera PiP rounded crop mask.",
                details={"input": key, "value": value, "error": str(exc)},
            ) from exc
    media_in = _find_fusion_tool(comp, "MediaIn")
    if not media_in:
        raise APICallFailed("Could not find MediaIn for camera PiP rounded crop.", details={"clip": clip_name})
    connection = _connect_mask_to_media_in(media_in, mask)
    return {
        "applied": True,
        "tool": getattr(mask, "Name", "RectangleMask"),
        "corner_radius": float(radius),
        "softness": float(softness),
        "connection": connection,
    }


def _timeline_video_items(conn) -> list[object]:
    items: list[object] = []
    try:
        track_count = int(conn.timeline.GetTrackCount("video") or 0)
    except Exception as exc:
        raise APICallFailed("Cannot inspect video tracks for social crop.", details={"track_type": "video"}) from exc
    for index in range(1, track_count + 1):
        try:
            items.extend(conn.timeline.GetItemListInTrack("video", index) or [])
        except Exception:
            continue
    return items


def _apply_social_timeline_resolution(conn, *, width: int, height: int) -> dict[str, object]:
    requested = {"timelineResolutionWidth": str(width), "timelineResolutionHeight": str(height)}
    attempts: list[dict[str, object]] = []

    for key, value in [("useCustomSettings", "1"), *requested.items()]:
        try:
            timeline_ops.set_timeline_setting(conn, key, value)
            attempts.append({"key": key, "value": value, "ok": True})
        except APICallFailed as exc:
            attempts.append(
                {
                    "key": key,
                    "value": value,
                    "ok": False,
                    "error": {
                        "code": exc.code,
                        "message": str(exc),
                        "details": exc.details,
                    },
                }
            )
        except Exception as exc:
            attempts.append(
                {
                    "key": key,
                    "value": value,
                    "ok": False,
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": str(exc),
                        "type": exc.__class__.__name__,
                    },
                }
            )

    readback: dict[str, object] = {}
    getter = getattr(conn.timeline, "GetSetting", None)
    if callable(getter):
        for key in requested:
            try:
                readback[key] = getter(key)
            except Exception:
                readback[key] = None

    verified = all(str(readback.get(key, "")) == value for key, value in requested.items()) if readback else all(
        attempt["ok"] for attempt in attempts if attempt["key"] in requested
    )
    failed = [attempt for attempt in attempts if not attempt["ok"]]
    return {
        "requested": requested,
        "status": "verified" if verified else "failed",
        "verified": verified,
        "readback": readback,
        "attempts": attempts,
        "failed": failed,
    }


def _set_camera_pip_transform(item: Any, *, zoom: float, pan: float, tilt: float, opacity: float) -> dict[str, object]:
    props = {"ZoomX": zoom, "ZoomY": zoom, "Pan": pan, "Tilt": tilt, "Opacity": opacity}
    failed: list[str] = []
    setter = getattr(item, "SetProperty", None)
    if not callable(setter):
        raise APICallFailed("Camera PiP requires TimelineItem.SetProperty support.")
    for key, value in props.items():
        try:
            result = setter(key, value)
        except Exception:
            result = False
        if result is False:
            failed.append(key)
    if failed:
        raise APICallFailed("Failed to apply camera PiP transform.", details={"failed_properties": failed})
    return props


def _camera_pip_item_matches(item: Any, camera_clip: str) -> bool:
    if camera_clip in {"*", "all", "ALL"}:
        return True
    try:
        name = str(item.GetName() or "")
    except Exception:
        name = ""
    candidates = {camera_clip, Path(camera_clip).name}
    stem = Path(camera_clip).stem
    if stem:
        candidates.add(stem)
    return any(candidate and candidate in name for candidate in candidates)


_CAMERA_PIP_ANCHORS = {
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
    "center",
}

_CAMERA_PIP_ANCHOR_ALIASES = {
    "tl": "top-left",
    "tr": "top-right",
    "bl": "bottom-left",
    "br": "bottom-right",
    "upper-left": "top-left",
    "upper-right": "top-right",
    "lower-left": "bottom-left",
    "lower-right": "bottom-right",
    "top_left": "top-left",
    "top_right": "top-right",
    "bottom_left": "bottom-left",
    "bottom_right": "bottom-right",
    "middle": "center",
    "centre": "center",
}


def _normalize_camera_pip_anchor(anchor: str | None) -> str | None:
    text = str(anchor or "").strip().lower().replace(" ", "-")
    if not text:
        return None
    normalized = _CAMERA_PIP_ANCHOR_ALIASES.get(text, text)
    if normalized not in _CAMERA_PIP_ANCHORS:
        raise ValidationError(
            "Camera PiP anchor must be one of: top-left, top-right, bottom-left, bottom-right, center.",
            details={"anchor": anchor, "supported": sorted(_CAMERA_PIP_ANCHORS)},
            recoverability="not_applicable",
        )
    return normalized


def _optional_positive_int(value: Any) -> int | None:
    try:
        parsed = int(float(str(value).strip()))
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _timeline_resolution_for_camera_pip(conn: Any) -> tuple[int, int]:
    timeline = getattr(conn, "timeline", None)
    getter = getattr(timeline, "GetSetting", None)
    settings: dict[str, Any] = {}
    if callable(getter):
        for key in ("timelineResolutionWidth", "timelineResolutionHeight"):
            try:
                settings[key] = getter(key)
            except TypeError:
                try:
                    all_settings = getter()
                    settings.update(all_settings if isinstance(all_settings, dict) else {})
                except Exception:
                    pass
                break
            except Exception:
                pass

    width = _optional_positive_int(settings.get("timelineResolutionWidth"))
    height = _optional_positive_int(settings.get("timelineResolutionHeight"))
    if width is None or height is None:
        raise APICallFailed(
            "Cannot resolve timeline resolution for anchored camera PiP placement.",
            details={
                "timelineResolutionWidth": settings.get("timelineResolutionWidth"),
                "timelineResolutionHeight": settings.get("timelineResolutionHeight"),
            },
        )
    return width, height


def _default_camera_pip_margin(width: int, height: int) -> float:
    return float(round(24.0 * (min(width, height) / 1080.0), 3))


def _round_layout_value(value: float) -> float:
    rounded = round(float(value), 6)
    return int(rounded) if rounded.is_integer() else rounded


def _camera_pip_anchor_placement(
    *,
    anchor: str,
    width: int,
    height: int,
    zoom: float,
    margin: float | None,
    strict_fit: bool = True,
) -> dict[str, Any]:
    margin_px = _default_camera_pip_margin(width, height) if margin is None else float(margin)
    if margin_px < 0:
        raise ValidationError("Camera PiP margin cannot be negative.", details={"margin": margin})

    pip_width = float(width) * float(zoom)
    pip_height = float(height) * float(zoom)
    if pip_width <= 0 or pip_height <= 0:
        raise ValidationError("Camera PiP zoom must produce a positive bounding box.", details={"zoom": zoom})
    estimated_fits = pip_width + (2 * margin_px) <= width and pip_height + (2 * margin_px) <= height
    if not estimated_fits and strict_fit:
        raise ValidationError(
            "Camera PiP placement does not fit inside the timeline frame.",
            details={
                "anchor": anchor,
                "margin_px": margin_px,
                "timeline": {"width": width, "height": height},
                "estimated_bbox_size": {"width": pip_width, "height": pip_height},
            },
            recoverability="not_applicable",
        )

    center_left = (float(width) - pip_width) / 2.0
    center_top = (float(height) - pip_height) / 2.0
    if anchor == "center":
        left = center_left
        top = center_top
    else:
        left = margin_px if anchor.endswith("left") else float(width) - margin_px - pip_width
        top = margin_px if anchor.startswith("top") else float(height) - margin_px - pip_height

    pan = left - center_left
    # DaVinci Resolve Tilt is inverted relative to rendered image Y movement: positive moves up.
    tilt = center_top - top
    bbox = {
        "left": _round_layout_value(left),
        "top": _round_layout_value(top),
        "right": _round_layout_value(left + pip_width),
        "bottom": _round_layout_value(top + pip_height),
        "width": _round_layout_value(pip_width),
        "height": _round_layout_value(pip_height),
    }
    edge_margins = {
        "left": _round_layout_value(left),
        "top": _round_layout_value(top),
        "right": _round_layout_value(float(width) - (left + pip_width)),
        "bottom": _round_layout_value(float(height) - (top + pip_height)),
    }
    return {
        "mode": "anchor",
        "anchor": anchor,
        "margin_px": _round_layout_value(margin_px),
        "timeline_resolution": {"width": width, "height": height},
        "estimated_bbox": bbox,
        "edge_margins": edge_margins,
        "transform": {
            "Pan": _round_layout_value(pan),
            "Tilt": _round_layout_value(tilt),
        },
        "assumptions": [
            "Estimated bbox assumes DaVinci Resolve uniform Zoom scales the PiP relative to the timeline frame.",
            "Use timeline frame-export for rendered pixel verification.",
        ],
        "estimated_fits": estimated_fits,
    }


def _read_camera_pip_properties(item: Any, keys: list[str]) -> dict[str, Any]:
    getter = getattr(item, "GetProperty", None)
    if not callable(getter):
        return {}
    props: dict[str, Any] = {}
    bulk_props: dict[str, Any] | None = None
    for key in keys:
        try:
            props[key] = getter(key)
            continue
        except TypeError:
            if bulk_props is None:
                try:
                    value = getter()
                    bulk_props = value if isinstance(value, dict) else {}
                except Exception:
                    bulk_props = {}
            props[key] = bulk_props.get(key)
        except Exception:
            props[key] = None
    return props


def _float_close(left: Any, right: Any, *, tolerance: float = 0.001) -> bool:
    try:
        return abs(float(left) - float(right)) <= tolerance
    except Exception:
        return False


def _verify_camera_pip_transform_properties(item: Any, expected: dict[str, object]) -> dict[str, Any]:
    keys = list(expected.keys())
    readback = _read_camera_pip_properties(item, keys)
    if not readback:
        return {
            "status": "unavailable",
            "property_readback_available": False,
            "expected_transform": expected,
            "readback": {},
            "render_verification": "not_performed_use_timeline_frame_export",
        }
    checks = {
        key: {
            "ok": _float_close(readback.get(key), value),
            "expected": value,
            "actual": readback.get(key),
        }
        for key, value in expected.items()
    }
    return {
        "status": "verified" if all(check["ok"] for check in checks.values()) else "failed",
        "property_readback_available": True,
        "expected_transform": expected,
        "readback": readback,
        "checks": checks,
        "render_verification": "not_performed_use_timeline_frame_export",
    }


def _camera_pip_verification_status(verifications: list[dict[str, Any]]) -> str:
    if not verifications:
        return "verified"
    statuses = {str(row.get("status") or "") for row in verifications}
    if statuses == {"verified"}:
        return "verified"
    if "failed" in statuses:
        return "failed"
    return "pending_manual"


def _paeth_predictor(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    if up_distance <= upper_left_distance:
        return up
    return upper_left


def _read_png_rgb(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise APICallFailed("Rendered placement verification requires PNG frame exports.", details={"path": str(path)})

    offset = 8
    width = height = bit_depth = color_type = interlace = None
    idat_parts: list[bytes] = []
    while offset + 8 <= len(data):
        length = int.from_bytes(data[offset:offset + 4], "big")
        chunk_type = data[offset + 4:offset + 8]
        chunk_data = data[offset + 8:offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width = int.from_bytes(chunk_data[0:4], "big")
            height = int.from_bytes(chunk_data[4:8], "big")
            bit_depth = chunk_data[8]
            color_type = chunk_data[9]
            interlace = chunk_data[12]
        elif chunk_type == b"IDAT":
            idat_parts.append(chunk_data)
        elif chunk_type == b"IEND":
            break

    if width is None or height is None or bit_depth != 8 or interlace != 0:
        raise APICallFailed(
            "Unsupported PNG format for rendered placement verification.",
            details={"path": str(path), "bit_depth": bit_depth, "interlace": interlace},
        )

    channels_by_color_type = {0: 1, 2: 3, 4: 2, 6: 4}
    channels = channels_by_color_type.get(int(color_type or -1))
    if channels is None:
        raise APICallFailed(
            "Unsupported PNG color type for rendered placement verification.",
            details={"path": str(path), "color_type": color_type},
        )

    raw = zlib.decompress(b"".join(idat_parts))
    stride = int(width) * channels
    expected = (stride + 1) * int(height)
    if len(raw) < expected:
        raise APICallFailed(
            "PNG frame export was truncated.",
            details={"path": str(path), "expected_min_bytes": expected, "actual_bytes": len(raw)},
        )

    rows: list[bytearray] = []
    position = 0
    previous = bytearray(stride)
    for _y in range(int(height)):
        filter_type = raw[position]
        position += 1
        scanline = bytearray(raw[position:position + stride])
        position += stride
        for index in range(stride):
            left = scanline[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                value = scanline[index]
            elif filter_type == 1:
                value = (scanline[index] + left) & 0xFF
            elif filter_type == 2:
                value = (scanline[index] + up) & 0xFF
            elif filter_type == 3:
                value = (scanline[index] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                value = (scanline[index] + _paeth_predictor(left, up, upper_left)) & 0xFF
            else:
                raise APICallFailed(
                    "Unsupported PNG filter for rendered placement verification.",
                    details={"path": str(path), "filter_type": filter_type},
                )
            scanline[index] = value
        rows.append(scanline)
        previous = scanline

    rgb = bytearray(int(width) * int(height) * 3)
    output_index = 0
    for row in rows:
        for x in range(int(width)):
            pixel_index = x * channels
            if color_type == 0:
                r = g = b = row[pixel_index]
            elif color_type == 4:
                r = g = b = row[pixel_index]
            else:
                r, g, b = row[pixel_index], row[pixel_index + 1], row[pixel_index + 2]
            rgb[output_index:output_index + 3] = bytes((r, g, b))
            output_index += 3
    return int(width), int(height), bytes(rgb)


def _measure_changed_png_bbox(
    foreground_path: Path,
    background_path: Path,
    *,
    diff_threshold: int,
) -> dict[str, Any]:
    fg_width, fg_height, fg_rgb = _read_png_rgb(foreground_path)
    bg_width, bg_height, bg_rgb = _read_png_rgb(background_path)
    if (fg_width, fg_height) != (bg_width, bg_height):
        raise APICallFailed(
            "Rendered placement verification frames have different dimensions.",
            details={
                "foreground": {"path": str(foreground_path), "width": fg_width, "height": fg_height},
                "background": {"path": str(background_path), "width": bg_width, "height": bg_height},
            },
        )

    threshold = max(1, min(255, int(diff_threshold)))
    min_x, min_y = fg_width, fg_height
    max_x = max_y = -1
    changed = 0
    total_diff = 0
    for pixel_index in range(fg_width * fg_height):
        byte_index = pixel_index * 3
        diff = max(
            abs(fg_rgb[byte_index] - bg_rgb[byte_index]),
            abs(fg_rgb[byte_index + 1] - bg_rgb[byte_index + 1]),
            abs(fg_rgb[byte_index + 2] - bg_rgb[byte_index + 2]),
        )
        if diff < threshold:
            continue
        x = pixel_index % fg_width
        y = pixel_index // fg_width
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x)
        max_y = max(max_y, y)
        changed += 1
        total_diff += diff

    if changed <= 0:
        raise APICallFailed(
            "Rendered placement verification could not detect the PiP overlay.",
            details={
                "foreground_path": str(foreground_path),
                "background_path": str(background_path),
                "diff_threshold": threshold,
            },
        )

    width = max_x - min_x + 1
    height = max_y - min_y + 1
    return {
        "image_size": {"width": fg_width, "height": fg_height},
        "bbox": {
            "left": min_x,
            "top": min_y,
            "right": max_x,
            "bottom": max_y,
            "width": width,
            "height": height,
        },
        "edge_margins": {
            "left": min_x,
            "top": min_y,
            "right": fg_width - 1 - max_x,
            "bottom": fg_height - 1 - max_y,
        },
        "changed_pixels": changed,
        "changed_fraction": round(changed / float(fg_width * fg_height), 6),
        "average_changed_diff": round(total_diff / float(changed), 3),
        "diff_threshold": threshold,
    }


def _camera_pip_margin_error(anchor: str, margins: dict[str, Any], *, target_margin: float) -> dict[str, float]:
    if anchor == "top-right":
        return {"x": float(margins["right"]) - target_margin, "y": float(margins["top"]) - target_margin}
    if anchor == "top-left":
        return {"x": target_margin - float(margins["left"]), "y": float(margins["top"]) - target_margin}
    if anchor == "bottom-right":
        return {"x": float(margins["right"]) - target_margin, "y": target_margin - float(margins["bottom"])}
    if anchor == "bottom-left":
        return {"x": target_margin - float(margins["left"]), "y": target_margin - float(margins["bottom"])}
    if anchor == "center":
        image = margins.get("_image_size") or {}
        bbox = margins.get("_bbox") or {}
        image_center_x = float(image.get("width", 0)) / 2.0
        image_center_y = float(image.get("height", 0)) / 2.0
        bbox_center_x = (float(bbox.get("left", 0)) + float(bbox.get("right", 0))) / 2.0
        bbox_center_y = (float(bbox.get("top", 0)) + float(bbox.get("bottom", 0))) / 2.0
        return {"x": image_center_x - bbox_center_x, "y": bbox_center_y - image_center_y}
    return {"x": 0.0, "y": 0.0}


def _camera_pip_margin_check(anchor: str, margins: dict[str, Any], *, target_margin: float, tolerance_px: float) -> dict[str, Any]:
    image = margins.get("_image_size") or {}
    bbox = margins.get("_bbox") or {}
    image_width = float(image.get("width", 0) or 0)
    image_height = float(image.get("height", 0) or 0)
    bbox_width = float(bbox.get("width", 0) or 0)
    bbox_height = float(bbox.get("height", 0) or 0)
    fits_with_margin = (
        image_width <= 0
        or image_height <= 0
        or (
            bbox_width + (2 * target_margin) <= image_width + tolerance_px
            and bbox_height + (2 * target_margin) <= image_height + tolerance_px
        )
    )
    if anchor == "center":
        error = _camera_pip_margin_error(anchor, margins, target_margin=target_margin)
        return {
            "anchor": anchor,
            "target": "center",
            "tolerance_px": tolerance_px,
            "offset_px": {"x": _round_layout_value(error["x"]), "y": _round_layout_value(error["y"])},
            "fits_with_margin": fits_with_margin,
            "ok": fits_with_margin and abs(error["x"]) <= tolerance_px and abs(error["y"]) <= tolerance_px,
        }
    edge_names = {
        "top-right": ("top", "right"),
        "top-left": ("top", "left"),
        "bottom-right": ("bottom", "right"),
        "bottom-left": ("bottom", "left"),
    }[anchor]
    values = {edge: float(margins[edge]) for edge in edge_names}
    errors = {edge: _round_layout_value(values[edge] - target_margin) for edge in edge_names}
    return {
        "anchor": anchor,
        "target_margin_px": _round_layout_value(target_margin),
        "tolerance_px": _round_layout_value(tolerance_px),
        "measured_edges": {edge: _round_layout_value(values[edge]) for edge in edge_names},
        "errors_px": errors,
        "fits_with_margin": fits_with_margin,
        "ok": fits_with_margin and all(abs(float(error)) <= tolerance_px for error in errors.values()),
    }
