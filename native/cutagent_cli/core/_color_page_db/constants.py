"""Color Page DB param keys and fixture constants."""

from __future__ import annotations

import base64

# ---------------------------------------------------------------------------
# Param-key constants (confirmed via DB dump analysis 2026-04-04)
# ---------------------------------------------------------------------------

# Primary Wheels – Lift (CDL Offset)
PARAM_LIFT_Y = 0x06000017  # Master Lift (Y) – inferred from range
PARAM_LIFT_R = 0x06000018
PARAM_LIFT_G = 0x06000019
PARAM_LIFT_B = 0x0600001A

# Primary Wheels – Gain (CDL Slope)
PARAM_GAIN_Y = 0x0600001C  # Master Gain (Y) – inferred from range
PARAM_GAIN_R = 0x0600001D
PARAM_GAIN_G = 0x0600001E
PARAM_GAIN_B = 0x0600001F
PARAM_GAIN_MASTER = 0x06000020  # GUI fourth Gain numeric field, confirmed by HSV-node fixture

# Primary Wheels – Gamma (CDL Power)
PARAM_GAMMA_Y = 0x06000021  # Master Gamma (Y) – inferred from range
PARAM_GAMMA_R = 0x06000022
PARAM_GAMMA_G = 0x06000023
PARAM_GAMMA_B = 0x06000024
PARAM_GAMMA_MASTER = 0x06000025  # GUI fourth Gamma numeric field, confirmed by HSV-node fixture

# Primary Controls (confirmed 2026-04-04)
PARAM_SATURATION = 0x06000005  # confirmed (UI/50: UI 65 → 1.3)
PARAM_HUE = 0x06000004  # confirmed ((UI-50)/50: UI 60 → 0.2)
PARAM_CONTRAST = 0x860000C1  # confirmed (direct: UI 1.5 → 1.5)
PARAM_PIVOT = 0x860000C0  # confirmed (direct: UI 0.6 → 0.6)
PARAM_TEMPERATURE = 0x86000115  # confirmed (direct: UI 50 → 50)
PARAM_TINT = 0x86000116  # confirmed (direct: UI 25 → 25)
PARAM_LUM_MIX = 0x8600000B  # confirmed (UI 75 → internal 0.75, range 0-1)
PARAM_HIGHLIGHTS = 0x86000110  # confirmed
PARAM_SHADOWS = 0x86000111  # confirmed
PARAM_COLOR_BOOST = 0x86000112  # confirmed
PARAM_MID_DETAIL = 0x86000113  # confirmed

# Color Slice (GUI-authored fixtures captured in DaVinci Resolve Studio 21.0.0.47).
PARAM_COLOR_SLICE_GLOBAL_DEN = 0x86000600
PARAM_COLOR_SLICE_GLOBAL_DEN_DEPTH = 0x86000601
PARAM_COLOR_SLICE_GLOBAL_SAT = 0x86000602
PARAM_COLOR_SLICE_GLOBAL_SAT_BALANCE = 0x86000603
PARAM_COLOR_SLICE_GLOBAL_SAT_DEPTH = 0x86000604
PARAM_COLOR_SLICE_GLOBAL_HUE = 0x86000605
PARAM_COLOR_SLICE_PER_SLICE = 0x86000606
PARAM_COLOR_SLICE_CENTER = 0x86000607
PARAM_COLOR_WARPER_HUE_SAT_WIDTH = 0x8600012C
PARAM_COLOR_WARPER_HUE_SAT_HEIGHT = 0x8600012D
PARAM_COLOR_WARPER_CHROMA_LUMA_WIDTH = 0x8600012E
PARAM_COLOR_WARPER_CHROMA_LUMA_HEIGHT = 0x8600012F
PARAM_COLOR_WARPER_HUE_SAT_SELECTION = 0x86000130
PARAM_COLOR_WARPER_CHROMA_LUMA_SELECTION = 0x86000131
PARAM_COLOR_WARPER_MODE = 0x86000136
PARAM_COLOR_WARPER_SUBMODE = 0x86000137
PARAM_COLOR_WARPER_CHROMA_STROKE = 0x86000138
PARAM_COLOR_WARPER_PANEL_MODE = 0x8600013A
COLOR_SLICE_NAMES = ("red", "skin", "yellow", "green", "cyan", "blue", "magenta")

# Node enable (from binary analysis)
PARAM_NODE_ENABLE = 0xC0000001
PARAM_LAYER_MIXER_COMPOSITE_MODE = 0xC0000043

# Offset wheel (confirmed 2026-04-04, UI 120 → internal 3.8 → transform (UI-25)/25)
PARAM_OFFSET_Y = 0x0600007C  # inferred (master)
PARAM_OFFSET_R = 0x0600007D  # confirmed
PARAM_OFFSET_G = 0x0600007E  # confirmed
PARAM_OFFSET_B = 0x0600007F  # confirmed


# Qualifier (Node 1 in grade section, confirmed 2026-04-04)
PARAM_QUAL_HUE_CENTER = 0x0830000E  # confirmed: qualifier hue center (float)
PARAM_QUAL_HUE_WIDTH = 0x0830000F
PARAM_QUAL_HUE_SYMMETRY = 0x08300010
PARAM_QUAL_HUE_SOFT = 0x08300011
PARAM_QUAL_SAT_HIGH_CLIP = 0x08300012
PARAM_QUAL_SAT_LOW_CLIP = 0x08300013
PARAM_QUAL_SAT_HIGH_SOFT = 0x08300014
PARAM_QUAL_SAT_LOW_SOFT = 0x08300015
PARAM_QUAL_LUM_HIGH_CLIP = 0x08300016
PARAM_QUAL_LUM_LOW_CLIP = 0x08300017
PARAM_QUAL_LUM_HIGH_SOFT = 0x08300018
PARAM_QUAL_LUM_LOW_SOFT = 0x08300019
PARAM_QUAL_HUE_WIDTH_COMPANION = 0x08300025
PARAM_QUAL_HUE_SOFT_COMPANION = 0x08300026
PARAM_QUAL_HSL_TOOL = 0x0830006F
PARAM_QUAL_MODE = 0x88300001  # confirmed: qualifier enable/mode (varint)
PARAM_QUAL_MATTE_BLUR_RADIUS = 0x86000051
# DaVinci Resolve 21 GUI-backed HSL/matte keys share numeric Project.db slots with the
# older qualifier helper below, but their UI meaning is palette-contextual.
PARAM_QUAL_SAT_CENTER = PARAM_QUAL_HUE_SYMMETRY
PARAM_QUAL_SAT_WIDTH = PARAM_QUAL_HUE_SOFT
PARAM_QUAL_SAT_HIGH_BOUND = PARAM_QUAL_SAT_HIGH_CLIP
PARAM_QUAL_SAT_LOW_BOUND = PARAM_QUAL_SAT_LOW_CLIP
PARAM_QUAL_SAT_LOW_CLEAN = PARAM_QUAL_SAT_HIGH_SOFT
PARAM_QUAL_SAT_HIGH_CLEAN = PARAM_QUAL_SAT_LOW_SOFT
PARAM_QUAL_LUMA_HIGH_BOUND = PARAM_QUAL_LUM_HIGH_CLIP
PARAM_QUAL_LUMA_LOW_BOUND = PARAM_QUAL_LUM_LOW_CLIP
PARAM_QUAL_LUMA_LOW_SOFT_LEGACY = PARAM_QUAL_LUM_HIGH_SOFT
PARAM_QUAL_LUMA_HIGH_SOFT_LEGACY = PARAM_QUAL_LUM_LOW_SOFT
PARAM_QUAL_LUMA_CENTER = PARAM_QUAL_LUMA_HIGH_BOUND
PARAM_QUAL_LUMA_WIDTH = PARAM_QUAL_LUMA_LOW_BOUND
PARAM_QUAL_LUMA_LOW_SOFT = PARAM_QUAL_LUMA_LOW_SOFT_LEGACY
PARAM_QUAL_LUMA_HIGH_SOFT = PARAM_QUAL_LUMA_HIGH_SOFT_LEGACY
PARAM_QUAL_HUE_LOW_SOFT = PARAM_QUAL_HUE_WIDTH_COMPANION
PARAM_QUAL_HUE_HIGH_SOFT = PARAM_QUAL_HUE_SOFT_COMPANION
PARAM_QUAL_MATTE_MODE = PARAM_QUAL_HSL_TOOL
PARAM_QUAL_MATTE_BLUR = 0x0C300020
PARAM_QUAL_MATTE_CLEAN_BLACK = 0x0C300031
PARAM_QUAL_MATTE_CLEAN_WHITE = 0x0C300032

# Window (Node 2 in grade section, confirmed 2026-04-04)
PARAM_WIN_SOFT_TOP = 0x08700009  # soft edge top
PARAM_WIN_SOFT_RIGHT = 0x0870000A  # soft edge right
PARAM_WIN_SOFT_BOTTOM = 0x0870000B  # soft edge bottom
PARAM_WIN_SOFT_LEFT = 0x0870000C  # soft edge left
PARAM_WIN_POS_X = 0x08700015  # position X
PARAM_WIN_POS_Y = 0x08700016  # position Y
PARAM_WIN_SIZE_W = 0x08700017  # size width
PARAM_WIN_SIZE_H = 0x08700018  # size height
PARAM_WIN_ROTATION = 0x0870001C  # rotation
PARAM_WIN_TILT = 0x0870001D  # tilt
PARAM_WIN_SHAPE = 0x88700012  # shape flag

# Curves (bytes-encoded control points in Node 0, confirmed 2026-04-04)
# Each curve = protobuf with repeated {X: float32, Y: float32} points (0-1024 range)
PARAM_CURVE_Y = 0x86000506  # Y/Luma custom curve (bytes)
PARAM_CURVE_R = 0x86000507  # Red custom curve (bytes)
PARAM_CURVE_G = 0x86000508  # Green custom curve (bytes)
PARAM_CURVE_B = 0x86000509  # Blue custom curve (bytes)

# Curves mode flags (appear when curves panel is active)
PARAM_CURVES_MODE = 0x8600009B  # curves display mode
PARAM_CURVES_LINK = 0x860000BB  # curves link mode

# Custom Curves endpoint values (GUI Edit fields, confirmed in DaVinci Resolve 21.0.0b.20)
# GUI value 80 -> DB value 0.6, so internal = (ui - 50) / 50.
PARAM_CURVE_HIGH_Y = 0x0600002A
PARAM_CURVE_HIGH_R = 0x0600002B
PARAM_CURVE_HIGH_G = 0x0600002C
PARAM_CURVE_HIGH_B = 0x0600002D

# Hue curve payloads (GUI fixture-backed in DaVinci Resolve Studio 21.0.0b.20).
# GUI Input Hue 348.01 / Hue Rotate 135.20 persisted as:
#   x = (input_hue - 256) / 360
#   y = (180 - hue_rotate) / 360
# GUI Hue Vs Sat Input Hue 110.70 / Saturation 1.97 persisted as:
#   x = (input_hue - 256) / 360
#   y = (2 - saturation) / 2
# GUI Hue Vs Lum Input Hue 110.70 / Lum Gain 1.97 uses the same x/y payload
# mapping plus mode discriminator 0x86000118=2.
# with wrap-around companion points at half-cycle offsets.
PARAM_HUE_CURVE_MODE = 0x860000B7
PARAM_HUE_VS_SAT_MODE = 0x860000B8
PARAM_HUE_VS_LUM_MODE = 0x860000B9
PARAM_HUE_CURVE_VARIANT = 0x860000CF
PARAM_HUE_VS_LUM_SELECTOR = 0x86000118
PARAM_HUE_VS_HUE_CURVE = 0x86000400
PARAM_HUE_VS_SAT_CURVE = 0x86000401
PARAM_HUE_VS_LUM_CURVE = 0x86000402
PARAM_SAT_VS_SAT_SELECTOR = 0x86000103
PARAM_SAT_VS_SAT_CURVE = 0x86000404
PARAM_SAT_VS_LUM_SELECTOR = 0x86000202
PARAM_SAT_VS_LUM_CURVE = 0x86000405
PARAM_LUM_VS_SAT_SELECTOR = 0x860000BA
PARAM_LUM_VS_SAT_CURVE = 0x86000403

SAT_VS_SAT_FIXTURE_INPUT = 0.29818958044052124
SAT_VS_SAT_FIXTURE_OUTPUT = 1.9733333326876163
SAT_VS_SAT_FIXTURE_PAYLOAD = base64.b64decode(
    "CgUVAAAAPwoKDc+SbD4VS3mfPgoKDU6smD4VDnRaPAoKDU2sGD8VDnRaPAoKDSdWTD8VDnRaPAoKDe0EXz8VfnewPgoKDQAAgD8VAAAAPw=="
)
SAT_VS_SAT_LEFT_DX = SAT_VS_SAT_FIXTURE_INPUT - 0.23102878034114838
SAT_VS_SAT_RIGHT_DX = 0.8711689114570618 - SAT_VS_SAT_FIXTURE_INPUT
SAT_VS_SAT_LEFT_BLEND = (0.3114722669124603 - 0.5) / (0.013333333656191826 - 0.5)
SAT_VS_SAT_RIGHT_BLEND = (0.3446616530418396 - 0.5) / (0.013333333656191826 - 0.5)

# Native Color Page Circle Power Window payload (confirmed in DaVinci Resolve Studio 21.0.0b.20).
# The GUI-created Circle adds a second Color Page node-like block plus a node-order marker.
PARAM_POWER_WINDOW_SHAPE = 0x88500008  # 2 = circle in the GUI-created fixture
PARAM_POWER_WINDOW_INVERT = 0x8850000A  # GUI outside/invert toggle; fixture value 2 = outside
PARAM_POWER_WINDOW_OPACITY = 0x08500012  # GUI Circle opacity as normalized 0..1 float
PARAM_POWER_WINDOW_SIZE = 0x8850000D
PARAM_POWER_WINDOW_X_OFFSET = 0x8850000E  # writes/readbacks, no visible default-circle effect
PARAM_POWER_WINDOW_Y_OFFSET = 0x8850000F
PARAM_POWER_WINDOW_SOFT_1 = 0x08500005  # GUI Soft 1; GUI value 20.00 -> DB 320.0
PARAM_POWER_WINDOW_GUI_PAN = 0x0850000B  # GUI Pan; 50.00 center -> 0, 40.00 -> -819.2
PARAM_POWER_WINDOW_GUI_TILT = 0x0850000C  # GUI Tilt; 50.00 center -> 0, 40.00 -> -819.2
PARAM_POWER_WINDOW_GRADIENT_SHAPE = 0x08F00001  # Observed 2 in the GUI-created fixture, but not stable after reload probes.
PARAM_POWER_WINDOW_GRADIENT_ROTATE_MARKER = 0x08F00003  # Nonzero marker affects GUI Rotate +/-180, not arbitrary angle.
PARAM_POWER_WINDOW_GRADIENT_PAN = 0x08F00005  # GUI Pan; 50.00 center -> 0.0
PARAM_POWER_WINDOW_GRADIENT_TILT = 0x08F00006  # GUI Tilt; 50.00 center -> 0.0
PARAM_POWER_WINDOW_GRADIENT_4 = 0x08F00009
PARAM_POWER_WINDOW_GRADIENT_5 = 0x08F0000A
PARAM_POWER_WINDOW_GRADIENT_SOFT_1 = 0x08F0000B  # GUI Soft 1; GUI value 2.00 -> DB 200.0
PARAM_POWER_WINDOW_GRADIENT_ROTATE = PARAM_POWER_WINDOW_GRADIENT_ROTATE_MARKER
PARAM_POWER_WINDOW_GRADIENT_1 = PARAM_POWER_WINDOW_GRADIENT_ROTATE_MARKER
PARAM_POWER_WINDOW_GRADIENT_2 = PARAM_POWER_WINDOW_GRADIENT_PAN
PARAM_POWER_WINDOW_GRADIENT_3 = PARAM_POWER_WINDOW_GRADIENT_TILT
PARAM_POWER_WINDOW_GRADIENT_SIZE = PARAM_POWER_WINDOW_GRADIENT_SOFT_1
PARAM_POWER_WINDOW_LINEAR_1 = 0x08700009
PARAM_POWER_WINDOW_LINEAR_2 = 0x0870000A
PARAM_POWER_WINDOW_LINEAR_3 = 0x0870000B
PARAM_POWER_WINDOW_LINEAR_4 = 0x0870000C
PARAM_POWER_WINDOW_LINEAR_POINTS = 0x08700014
PARAM_POWER_WINDOW_LINEAR_5 = 0x08700015
PARAM_POWER_WINDOW_LINEAR_6 = 0x08700016
PARAM_POWER_WINDOW_LINEAR_7 = 0x08700017
PARAM_POWER_WINDOW_LINEAR_8 = 0x08700018
PARAM_POWER_WINDOW_LINEAR_9 = 0x0870001C
PARAM_POWER_WINDOW_LINEAR_10 = 0x0870001D
PARAM_POWER_WINDOW_LINEAR_OPACITY = 0x08700020  # GUI Opacity; 50.00 -> 0.5
PARAM_POWER_WINDOW_LINEAR_SHAPE = 0x8870000F  # 2 = linear in the GUI-created fixture
PARAM_POWER_WINDOW_LINEAR_11 = 0x88700012
PARAM_POWER_WINDOW_POLYGON_SHAPE = 0x08B00002  # 2 = polygon in the GUI-created fixture
PARAM_POWER_WINDOW_POLYGON_1 = 0x08B00004
PARAM_POWER_WINDOW_POLYGON_POINTS = 0x08B00006
PARAM_POWER_WINDOW_POLYGON_2 = 0x08B00007
PARAM_POWER_WINDOW_POLYGON_3 = 0x08B00008
PARAM_POWER_WINDOW_POLYGON_4 = 0x08B00009
PARAM_POWER_WINDOW_POLYGON_5 = 0x08B0000A
PARAM_POWER_WINDOW_POLYGON_6 = 0x08B0000E
PARAM_POWER_WINDOW_POLYGON_7 = 0x08B0000F
PARAM_POWER_WINDOW_CURVE_SHAPE = 0x08D00002  # 2 = curve in the GUI-created fixture
PARAM_POWER_WINDOW_CURVE_1 = 0x08D00004
PARAM_POWER_WINDOW_CURVE_POINTS_1 = 0x08D00006
PARAM_POWER_WINDOW_CURVE_POINTS_2 = 0x08D00007
PARAM_POWER_WINDOW_CURVE_POINTS_3 = 0x08D00008
PARAM_POWER_WINDOW_CURVE_2 = 0x08D00009
PARAM_POWER_WINDOW_CURVE_3 = 0x08D0000A
PARAM_POWER_WINDOW_CURVE_4 = 0x08D0000B
PARAM_POWER_WINDOW_CURVE_5 = 0x08D0000C
PARAM_POWER_WINDOW_CURVE_CENTER_X = 0x08D00010
PARAM_POWER_WINDOW_CURVE_CENTER_Y = 0x08D00011
POWER_WINDOW_CIRCLE_SHAPE_CODE = 2
POWER_WINDOW_GRADIENT_SHAPE_CODE = 2
POWER_WINDOW_LINEAR_SHAPE_CODE = 2
POWER_WINDOW_POLYGON_SHAPE_CODE = 2
POWER_WINDOW_CURVE_SHAPE_CODE = 2
POWER_WINDOW_SOFT_1_SCALE = 16.0
POWER_WINDOW_LINEAR_SOFT_SCALE = 16.0
POWER_WINDOW_LINEAR_OPACITY_SCALE = 100.0
POWER_WINDOW_GRADIENT_SOFT_1_SCALE = 100.0
POWER_WINDOW_GUI_PAN_CENTER = 50.0
POWER_WINDOW_GUI_PAN_SCALE = 81.92
POWER_WINDOW_GUI_TILT_CENTER = 50.0
POWER_WINDOW_GUI_TILT_SCALE = 81.92
POWER_WINDOW_NODE_ORDER = bytes.fromhex("0304050612848004")
POWER_WINDOW_GRADIENT_NODE_ORDER = bytes.fromhex("0304050612928004")
POWER_WINDOW_LINEAR_NODE_ORDER = bytes.fromhex("0304050612838004")
POWER_WINDOW_POLYGON_NODE_ORDER = bytes.fromhex("0304050612858004")
POWER_WINDOW_CURVE_NODE_ORDER = bytes.fromhex("0304050612868004")
POWER_WINDOW_GRADIENT_GUI_NODE_HEADER = bytes.fromhex("08928008")
POWER_WINDOW_GRADIENT_LEGACY_NODE_HEADER = bytes.fromhex("08928004")
NODE_LABEL_FIELD = 6
POWER_WINDOW_CIRCLE_NODE_TEMPLATE = bytes.fromhex(
    "08848004180132cb0112c80108011a0c088180c04212050d00000000"
    "1a0c088480c04212050d000000001a0c088580c04212050da72c0442"
    "1a0c088680c04212050d0000803f1a0c088b80c04212050d00000000"
    "1a0c088c80c04212050d000000001a0a088880c0c208120210021a0d"
    "088d80c0c20812050d000090431a0d088e80c0c20812050d00000000"
    "1a0d088f80c0c20812050d000000001a37089080c0c208122f522d0d"
    "0000803f15000000001d0000000025000000002d0000803f35000000"
    "003d0000000045000000004d0000803f"
)
POWER_WINDOW_GRADIENT_NODE_TEMPLATE = bytes.fromhex(
    "089280081801329d01129a0108011a09088180c047120210021a0c"
    "088380c04712050d000000001a0c088580c04712050d000000001a"
    "0c088680c04712050d000000001a0c088980c04712050d00000000"
    "1a0c088a80c04712050d000000001a0c088b80c04712050d000048"
    "431a37088d80c0c708122f522d0d0000803f15000000001d000000"
    "0025000000002d0000803f35000000003d0000000045000000004d"
    "0000803f"
)
POWER_WINDOW_LINEAR_NODE_TEMPLATE = bytes.fromhex(
    "08838004180132a002129d0208011a0c088980c04312050d0000a041"
    "1a0c088a80c04312050d0000a0411a0c088b80c04312050d0000a041"
    "1a0c088c80c04312050d0000a0411a39089480c04312324a300a0a"
    "0d0000c0c315000058c30a0a0d0000c0c315000058430a0a0d0000"
    "c04315000058430a0a0d0000c04315000058c31a0c089580c04312"
    "050d000000001a0c089680c04312050d000000001a0c089780c04312"
    "050d0000803f1a0c089880c04312050d0000803f1a0c089c80c04312"
    "050d000000001a0c089d80c04312050d000000001a0a088f80c0c308"
    "120210021a0d089280c0c30812050d000000001a37089e80c0c308"
    "122f522d0d0000803f15000000001d0000000025000000002d0000"
    "803f35000000003d0000000045000000004d0000803f"
)
POWER_WINDOW_POLYGON_NODE_TEMPLATE = bytes.fromhex(
    "08858004180132e60112e30108011a09088280c045120210021a0c088480c045"
    "12050d000000001a39088680c04512324a300a0a0d0000f0c315000087c30a"
    "0a0d0000f0c315000087430a0a0d0000f04315000087430a0a0d0000f043"
    "15000087c31a0c088780c04512050d000000001a0c088880c04512050d0000"
    "00001a0c088980c04512050d0000803f1a0c088a80c04512050d0000803f"
    "1a0c088e80c04512050d000000001a0c088f80c04512050d000000001a37"
    "089280c0c508122f522d0d0000803f15000000001d0000000025000000002d"
    "0000803f35000000003d0000000045000000004d0000803f"
)
POWER_WINDOW_CURVE_NODE_TEMPLATE = bytes.fromhex(
    "08868004180132cc0112c90108011a09088280c046120210021a0c088480c046"
    "12050d000000001a09088680c04612024a001a09088780c04612024a001a09"
    "088880c04612024a001a0c088980c04612050d000000001a0c088a80c04612"
    "050d000000001a0c088b80c04612050d0000803f1a0c088c80c04612050d"
    "0000803f1a0c089080c04612050d000000001a0c089180c04612050d0000"
    "00001a37089480c0c608122f522d0d0000803f15000000001d0000000025"
    "000000002d0000803f35000000003d0000000045000000004d0000803f"
)

# RGB Mixer (confirmed 2026-04-04, Node 0)
PARAM_RGB_MIXER_R = 0x86000052  # RGB Mixer channel adjustment
PARAM_RGB_MIXER_G = 0x86000053  # RGB Mixer channel adjustment
PARAM_RGB_MIXER_B = 0x86000054  # RGB Mixer channel adjustment
PARAM_RGB_MIXER_MONOCHROME_MODE = 0x860000A6  # RGB Mixer Monochrome + Preserve Luminance mode

# HDR Wheels (confirmed 2026-04-04, Node 0, key range 0x860000A7-AF)
PARAM_HDR_DARK_1 = 0x860000A7   # HDR Dark wheel
PARAM_HDR_DARK_2 = 0x860000A8
PARAM_HDR_DARK_3 = 0x860000A9
PARAM_HDR_SHADOW_1 = 0x860000AA  # HDR Shadow wheel
PARAM_HDR_SHADOW_2 = 0x860000AB
PARAM_HDR_SHADOW_3 = 0x860000AC
PARAM_HDR_LIGHT_1 = 0x860000AD   # HDR Light wheel
PARAM_HDR_LIGHT_2 = 0x860000AE
PARAM_HDR_LIGHT_3 = 0x860000AF

HDR_ZONE_PARAM_KEYS: dict[str, dict[str, int]] = {
    "dark": {
        "x": PARAM_HDR_DARK_1,
        "y": PARAM_HDR_DARK_2,
        "z": PARAM_HDR_DARK_3,
    },
    "shadow": {
        "x": PARAM_HDR_SHADOW_1,
        "y": PARAM_HDR_SHADOW_2,
        "z": PARAM_HDR_SHADOW_3,
    },
    "light": {
        "x": PARAM_HDR_LIGHT_1,
        "y": PARAM_HDR_LIGHT_2,
        "z": PARAM_HDR_LIGHT_3,
    },
}

# HDR Global control (bytes-encoded, Node 0, fixture-backed in DaVinci Resolve Studio 21.0.0b.20)
PARAM_HDR_GLOBAL_CONTROL = 0x86000305
PARAM_HDR_CONTROL_FLAGS = 0x86000309

HDR_DETAIL_ZONE_NAMES: dict[str, str] = {
    "highlight": "Highlight",
    "specular": "Specular",
}

# HDR detail payload shares the palette-contextual byte keys with the HDR Global control.
PARAM_HDR_DETAIL_VECTOR = 0x86000305
PARAM_HDR_DETAIL_RANGE = 0x86000306
PARAM_HDR_DETAIL_FLAGS = 0x86000309

HDR_DETAIL_RANGE_DEFAULTS: dict[str, dict[str, float]] = {
    "highlight": {"range_upper": 1.5, "range": 1.5, "anchor": 0.2, "falloff": 0.7121499180793762},
    "specular": {"range_upper": 4.0, "range": 4.0, "anchor": 0.1, "falloff": 0.1},
}

# Motion Effects / Blur (bytes-encoded, Node 0)
PARAM_MOTION_NR = PARAM_HDR_GLOBAL_CONTROL     # legacy alias; this key is palette-contextual
PARAM_BLUR_DATA = 0x86000306     # Blur data (bytes)
PARAM_MOTION_FLAGS = PARAM_HDR_CONTROL_FLAGS  # legacy alias; this key is palette-contextual

# Sizing/Transform (Node 3, key range 0x0C40XXXX)
PARAM_SIZING_ZOOM_X = 0x0C400002  # Zoom X
PARAM_SIZING_ZOOM_Y = 0x0C400003  # Zoom Y
PARAM_SIZING_POS = 0x0C400004     # Position offset
PARAM_SIZING_PAN_X = 0x0C40000B   # Pan X
PARAM_SIZING_PAN_Y = 0x0C40000C   # Pan Y
PARAM_SIZING_ROTATE = 0x0C40000D  # Rotation

# Key palette (fixture-backed in DaVinci Resolve Studio 21.0.0b.20)
PARAM_KEY_OUTPUT_GAIN = 0x0C30001D  # Key Output Gain

KEY_OUTPUT_NODE_TEMPLATE = bytes.fromhex(
    "080918013212121008011a0c089d80c06112050d0000803f"
)

SERIAL_NODE_GRAPH_ORDER = bytes.fromhex("12050304050612")
SERIAL_NODE_EMPTY_TOOLS = bytes.fromhex("0a0a08818080800c12021002")

LAYER_MIXER_TYPE = 90
LAYER_MIXER_COMPOSITE_MODES: dict[str, int] = {
    "normal": 0,
    # Verified from DaVinci Resolve Studio 21.0.0b.20 GUI
    # Composite Mode > Overlay fixture. Other menu entries remain
    # unpromoted until each has the same GUI/DB/render proof.
    "overlay": 12,
}
LAYER_MIXER_COMPOSITE_MODE_LABELS = {
    value: key.title() for key, value in LAYER_MIXER_COMPOSITE_MODES.items()
}
LAYER_MIXER_COMPOSITE_MODE_LABELS[0] = "Normal"
LAYER_MIXER_COMPOSITE_MODE_LABELS[14] = "Overlay"
LAYER_MIXER_BRANCH_NODE_INDEX = 2
LAYER_MIXER_NODE_INDEX = 3
LAYER_MIXER_PRIMARY_EDGE_SLOT = 2
LAYER_MIXER_BRANCH_EDGE_SLOT = 3
LAYER_MIXER_RENDER_PRIMARY_PORT = 6
LAYER_MIXER_RENDER_BRANCH_PORT = 5

# Human-readable name map
PARAM_NAMES: dict[int, str] = {
    PARAM_SATURATION: "saturation",
    PARAM_HUE: "hue",
    PARAM_CONTRAST: "contrast",
    PARAM_PIVOT: "pivot",
    PARAM_TEMPERATURE: "temperature",
    PARAM_TINT: "tint",
    PARAM_LIFT_R: "lift_r", PARAM_LIFT_G: "lift_g", PARAM_LIFT_B: "lift_b",
    PARAM_GAIN_R: "gain_r", PARAM_GAIN_G: "gain_g", PARAM_GAIN_B: "gain_b", PARAM_GAIN_MASTER: "gain_master",
    PARAM_GAMMA_R: "gamma_r", PARAM_GAMMA_G: "gamma_g", PARAM_GAMMA_B: "gamma_b", PARAM_GAMMA_MASTER: "gamma_master",
    PARAM_OFFSET_R: "offset_r", PARAM_OFFSET_G: "offset_g", PARAM_OFFSET_B: "offset_b",
    PARAM_LUM_MIX: "lum_mix",
    PARAM_HIGHLIGHTS: "highlights",
    PARAM_SHADOWS: "shadows",
    PARAM_COLOR_BOOST: "color_boost",
    PARAM_MID_DETAIL: "mid_detail",
    PARAM_QUAL_MATTE_BLUR_RADIUS: "qualifier_matte_blur_radius",
    PARAM_COLOR_SLICE_GLOBAL_DEN: "color_slice_global_den",
    PARAM_COLOR_SLICE_GLOBAL_DEN_DEPTH: "color_slice_global_den_depth",
    PARAM_COLOR_SLICE_GLOBAL_SAT: "color_slice_global_sat",
    PARAM_COLOR_SLICE_GLOBAL_SAT_BALANCE: "color_slice_global_sat_balance",
    PARAM_COLOR_SLICE_GLOBAL_SAT_DEPTH: "color_slice_global_sat_depth",
    PARAM_COLOR_SLICE_GLOBAL_HUE: "color_slice_global_hue",
    PARAM_COLOR_SLICE_PER_SLICE: "color_slice_per_slice",
    PARAM_COLOR_SLICE_CENTER: "color_slice_center",
    PARAM_COLOR_WARPER_HUE_SAT_WIDTH: "color_warper_hue_sat_width",
    PARAM_COLOR_WARPER_HUE_SAT_HEIGHT: "color_warper_hue_sat_height",
    PARAM_COLOR_WARPER_CHROMA_LUMA_WIDTH: "color_warper_chroma_luma_width",
    PARAM_COLOR_WARPER_CHROMA_LUMA_HEIGHT: "color_warper_chroma_luma_height",
    PARAM_COLOR_WARPER_HUE_SAT_SELECTION: "color_warper_hue_sat_selection",
    PARAM_COLOR_WARPER_CHROMA_LUMA_SELECTION: "color_warper_chroma_luma_selection",
    PARAM_COLOR_WARPER_MODE: "color_warper_mode",
    PARAM_COLOR_WARPER_SUBMODE: "color_warper_submode",
    PARAM_COLOR_WARPER_CHROMA_STROKE: "color_warper_chroma_stroke",
    PARAM_COLOR_WARPER_PANEL_MODE: "color_warper_panel_mode",
    PARAM_CURVE_Y: "curve_y",
    PARAM_CURVE_R: "curve_r",
    PARAM_CURVE_G: "curve_g",
    PARAM_CURVE_B: "curve_b",
    PARAM_CURVES_MODE: "curves_mode",
    PARAM_CURVES_LINK: "curves_link",
    PARAM_CURVE_HIGH_Y: "curve_high_y",
    PARAM_CURVE_HIGH_R: "curve_high_r",
    PARAM_CURVE_HIGH_G: "curve_high_g",
    PARAM_CURVE_HIGH_B: "curve_high_b",
    PARAM_QUAL_HUE_CENTER: "qualifier_hue_center",
    PARAM_QUAL_HUE_WIDTH: "qualifier_hue_width",
    PARAM_QUAL_SAT_CENTER: "qualifier_saturation_center_legacy",
    PARAM_QUAL_SAT_WIDTH: "qualifier_saturation_mode_marker",
    PARAM_QUAL_SAT_HIGH_BOUND: "qualifier_saturation_high",
    PARAM_QUAL_SAT_LOW_BOUND: "qualifier_saturation_low",
    PARAM_QUAL_SAT_LOW_CLEAN: "qualifier_saturation_low_clean",
    PARAM_QUAL_SAT_HIGH_CLEAN: "qualifier_saturation_high_clean",
    PARAM_QUAL_LUMA_CENTER: "qualifier_luma_high",
    PARAM_QUAL_LUMA_WIDTH: "qualifier_luma_low",
    PARAM_QUAL_LUMA_LOW_SOFT: "qualifier_luma_low_soft",
    PARAM_QUAL_LUMA_HIGH_SOFT: "qualifier_luma_high_soft",
    PARAM_QUAL_HUE_LOW_SOFT: "qualifier_hue_low_soft",
    PARAM_QUAL_HUE_HIGH_SOFT: "qualifier_hue_high_soft",
    PARAM_QUAL_MATTE_MODE: "qualifier_matte_mode",
    PARAM_QUAL_MODE: "qualifier_mode",
    PARAM_QUAL_MATTE_BLUR: "qualifier_matte_blur",
    PARAM_QUAL_MATTE_CLEAN_BLACK: "qualifier_matte_clean_black",
    PARAM_QUAL_MATTE_CLEAN_WHITE: "qualifier_matte_clean_white",
    PARAM_HUE_CURVE_MODE: "hue_curve_mode",
    PARAM_HUE_VS_SAT_MODE: "hue_vs_sat_mode",
    PARAM_HUE_VS_LUM_MODE: "hue_vs_lum_mode",
    PARAM_HUE_CURVE_VARIANT: "hue_curve_variant",
    PARAM_HUE_VS_LUM_SELECTOR: "hue_vs_lum_selector",
    PARAM_HUE_VS_HUE_CURVE: "hue_vs_hue_curve",
    PARAM_HUE_VS_SAT_CURVE: "hue_vs_sat_curve",
    PARAM_HUE_VS_LUM_CURVE: "hue_vs_lum_curve",
    PARAM_SAT_VS_SAT_SELECTOR: "sat_vs_sat_selector",
    PARAM_SAT_VS_SAT_CURVE: "sat_vs_sat_curve",
    PARAM_SAT_VS_LUM_SELECTOR: "sat_vs_lum_selector",
    PARAM_SAT_VS_LUM_CURVE: "sat_vs_lum_curve",
    PARAM_LUM_VS_SAT_SELECTOR: "lum_vs_sat_selector",
    PARAM_LUM_VS_SAT_CURVE: "lum_vs_sat_curve",
    PARAM_POWER_WINDOW_SHAPE: "power_window_shape",
    PARAM_POWER_WINDOW_INVERT: "power_window_invert",
    PARAM_POWER_WINDOW_OPACITY: "power_window_opacity",
    PARAM_POWER_WINDOW_SIZE: "power_window_size",
    PARAM_POWER_WINDOW_X_OFFSET: "power_window_x_offset",
    PARAM_POWER_WINDOW_Y_OFFSET: "power_window_y_offset",
    PARAM_POWER_WINDOW_SOFT_1: "power_window_soft_1",
    PARAM_POWER_WINDOW_GUI_PAN: "power_window_pan",
    PARAM_POWER_WINDOW_GUI_TILT: "power_window_tilt",
    PARAM_POWER_WINDOW_GRADIENT_SHAPE: "power_window_gradient_shape",
    PARAM_POWER_WINDOW_GRADIENT_ROTATE_MARKER: "power_window_gradient_rotate_marker",
    PARAM_POWER_WINDOW_GRADIENT_PAN: "power_window_gradient_pan",
    PARAM_POWER_WINDOW_GRADIENT_TILT: "power_window_gradient_tilt",
    PARAM_POWER_WINDOW_GRADIENT_4: "power_window_gradient_param_4",
    PARAM_POWER_WINDOW_GRADIENT_5: "power_window_gradient_param_5",
    PARAM_POWER_WINDOW_GRADIENT_SOFT_1: "power_window_gradient_soft_1",
    PARAM_POWER_WINDOW_LINEAR_1: "power_window_linear_soft_1",
    PARAM_POWER_WINDOW_LINEAR_2: "power_window_linear_soft_2",
    PARAM_POWER_WINDOW_LINEAR_3: "power_window_linear_soft_3",
    PARAM_POWER_WINDOW_LINEAR_4: "power_window_linear_soft_4",
    PARAM_POWER_WINDOW_LINEAR_POINTS: "power_window_linear_points",
    PARAM_POWER_WINDOW_LINEAR_5: "power_window_linear_x",
    PARAM_POWER_WINDOW_LINEAR_6: "power_window_linear_y",
    PARAM_POWER_WINDOW_LINEAR_7: "power_window_linear_width",
    PARAM_POWER_WINDOW_LINEAR_8: "power_window_linear_height",
    PARAM_POWER_WINDOW_LINEAR_9: "power_window_linear_param_9",
    PARAM_POWER_WINDOW_LINEAR_10: "power_window_linear_param_10",
    PARAM_POWER_WINDOW_LINEAR_OPACITY: "power_window_linear_opacity",
    PARAM_POWER_WINDOW_LINEAR_SHAPE: "power_window_linear_shape",
    PARAM_POWER_WINDOW_LINEAR_11: "power_window_linear_param_11",
    PARAM_POWER_WINDOW_POLYGON_SHAPE: "power_window_polygon_shape",
    PARAM_POWER_WINDOW_POLYGON_1: "power_window_polygon_param_1",
    PARAM_POWER_WINDOW_POLYGON_POINTS: "power_window_polygon_points",
    PARAM_POWER_WINDOW_POLYGON_2: "power_window_polygon_param_2",
    PARAM_POWER_WINDOW_POLYGON_3: "power_window_polygon_param_3",
    PARAM_POWER_WINDOW_POLYGON_4: "power_window_polygon_param_4",
    PARAM_POWER_WINDOW_POLYGON_5: "power_window_polygon_param_5",
    PARAM_POWER_WINDOW_POLYGON_6: "power_window_polygon_param_6",
    PARAM_POWER_WINDOW_POLYGON_7: "power_window_polygon_param_7",
    PARAM_POWER_WINDOW_CURVE_SHAPE: "power_window_curve_shape",
    PARAM_POWER_WINDOW_CURVE_1: "power_window_curve_param_1",
    PARAM_POWER_WINDOW_CURVE_POINTS_1: "power_window_curve_points_1",
    PARAM_POWER_WINDOW_CURVE_POINTS_2: "power_window_curve_points_2",
    PARAM_POWER_WINDOW_CURVE_POINTS_3: "power_window_curve_points_3",
    PARAM_POWER_WINDOW_CURVE_2: "power_window_curve_param_2",
    PARAM_POWER_WINDOW_CURVE_3: "power_window_curve_param_3",
    PARAM_POWER_WINDOW_CURVE_4: "power_window_curve_param_4",
    PARAM_POWER_WINDOW_CURVE_5: "power_window_curve_param_5",
    PARAM_POWER_WINDOW_CURVE_CENTER_X: "power_window_curve_center_x",
    PARAM_POWER_WINDOW_CURVE_CENTER_Y: "power_window_curve_center_y",
    PARAM_RGB_MIXER_R: "rgb_mixer_r",
    PARAM_RGB_MIXER_G: "rgb_mixer_g",
    PARAM_RGB_MIXER_B: "rgb_mixer_b",
    PARAM_RGB_MIXER_MONOCHROME_MODE: "rgb_mixer_monochrome_mode",
    PARAM_HDR_DARK_1: "hdr_dark_x",
    PARAM_HDR_DARK_2: "hdr_dark_y",
    PARAM_HDR_DARK_3: "hdr_dark_z",
    PARAM_HDR_SHADOW_1: "hdr_shadow_x",
    PARAM_HDR_SHADOW_2: "hdr_shadow_y",
    PARAM_HDR_SHADOW_3: "hdr_shadow_z",
    PARAM_HDR_LIGHT_1: "hdr_light_x",
    PARAM_HDR_LIGHT_2: "hdr_light_y",
    PARAM_HDR_LIGHT_3: "hdr_light_z",
    PARAM_HDR_GLOBAL_CONTROL: "hdr_global_control",
    PARAM_HDR_CONTROL_FLAGS: "hdr_control_flags",
    PARAM_KEY_OUTPUT_GAIN: "key_output_gain",
}

QUALIFIER_HSL_PARAM_NAMES: dict[int, str] = {
    PARAM_QUAL_HUE_CENTER: "qualifier_hue_center",
    PARAM_QUAL_HUE_WIDTH: "qualifier_hue_width",
    PARAM_QUAL_HUE_SOFT: "qualifier_hue_soft",
    PARAM_QUAL_HUE_SYMMETRY: "qualifier_hue_symmetry",
    PARAM_QUAL_HUE_WIDTH_COMPANION: "qualifier_hue_width_companion",
    PARAM_QUAL_HUE_SOFT_COMPANION: "qualifier_hue_soft_companion",
    PARAM_QUAL_SAT_LOW_CLIP: "qualifier_sat_low_clip",
    PARAM_QUAL_SAT_HIGH_CLIP: "qualifier_sat_high_clip",
    PARAM_QUAL_SAT_LOW_SOFT: "qualifier_sat_low_soft",
    PARAM_QUAL_SAT_HIGH_SOFT: "qualifier_sat_high_soft",
    PARAM_QUAL_LUM_LOW_CLIP: "qualifier_lum_low_clip",
    PARAM_QUAL_LUM_HIGH_CLIP: "qualifier_lum_high_clip",
    PARAM_QUAL_LUM_LOW_SOFT: "qualifier_lum_low_soft",
    PARAM_QUAL_LUM_HIGH_SOFT: "qualifier_lum_high_soft",
    PARAM_QUAL_MATTE_BLUR_RADIUS: "qualifier_matte_blur_radius",
    PARAM_QUAL_HSL_TOOL: "qualifier_hsl_tool",
    PARAM_QUAL_MODE: "qualifier_mode",
}

PARAM_KEYS_BY_NAME: dict[str, int] = {name: key for key, name in PARAM_NAMES.items()}

# DaVinci Resolve Studio 21.0.0b.20 GUI fixture for the tutorial HSV saturation
# workflow: node color space set to HSV, channels 1/3 disabled, channel 2 active,
# then saturation adjusted through Primary Balance Gamma/Gain rather than the
# regular Sat knob. Captured from live Project.db after GUI manipulation on
# 2026-06-08 and kept as small protobuf grafts instead of a full clip grade so
# target clip resolution/version metadata can remain intact.
HSV_NODE_FIELD7_TEMPLATE_HEX = (
    "0801100120be0128b4013801402c4a94010a7a080118013274127208011a0c089d80803012050d"
    "8a3078401a0c089e80803012050d6f1456401a0c089f80803012050d4e047f401a0c08a080"
    "803012050d456260401a0c08a280803012050d5970243f1a0c08a380803012050d521b263f"
    "1a0c08a480803012050dd34d2b3d1a0c08a580803012050dbf8e183f0a0c089280041801"
    "3204120208011208030405061292800452300a0a08818080800c120210020a0a08d28080"
    "800c120220000a0a08d48080800c120220000a0a08968180800c1202102e60f6d393f29003"
)
HSV_NODE_ROOT_FIELD3_TEMPLATE_HEX = (
    "20be0128b401380140544a480a4308061801323d123b08011a37089480c0c608122f522d0d"
    "0000803f15000000001d0000000025000000002d0000803f35000000003d0000000045"
    "000000004d0000803f120106520c0a0a08818080800c120210026099933f"
)
HSV_NODE_DEFAULT_PARAMS: dict[int, float] = {
    PARAM_GAIN_R: 3.877963,
    PARAM_GAIN_G: 3.344997,
    PARAM_GAIN_B: 3.984638,
    PARAM_GAIN_MASTER: 3.505998,
    PARAM_GAMMA_R: 0.642339,
    PARAM_GAMMA_G: 0.648854,
    PARAM_GAMMA_B: 0.041822,
    PARAM_GAMMA_MASTER: 0.595928,
}

CST_OFX_PLUGIN_ID = "com.blackmagicdesign.resolvefx.colorspacetransformv2"
CST_PARAM_INPUT_COLOR_SPACE = "inputColorSpace"
CST_PARAM_INPUT_GAMMA = "inputGamma"
CST_PARAM_OUTPUT_COLOR_SPACE = "outputColorSpace"
CST_PARAM_OUTPUT_GAMMA = "outputGamma"
CST_PARAM_RESOLVEFX_VERSION = "resolvefxVersion"
CST_PARAM_NAMES = {
    CST_PARAM_INPUT_COLOR_SPACE,
    CST_PARAM_INPUT_GAMMA,
    CST_PARAM_OUTPUT_COLOR_SPACE,
    CST_PARAM_OUTPUT_GAMMA,
}
CST_TOOL_BLOCK_PATH = [1, 7, 10]
CST_TOOL_PARAM_PLUGIN_ID = 0xC0000049
CST_TOOL_PARAM_CONTEXT = 0xC000005E
CST_TOOL_PARAM_ENABLE_A = 0xC0000063
CST_TOOL_PARAM_OPTIONS = 0xC0000087
CST_TOOL_PARAM_ENABLE_B = 0xC00000D2
CST_TOOL_PARAM_KEYS = {
    CST_TOOL_PARAM_PLUGIN_ID,
    CST_TOOL_PARAM_CONTEXT,
    CST_TOOL_PARAM_ENABLE_A,
    CST_TOOL_PARAM_OPTIONS,
    CST_TOOL_PARAM_ENABLE_B,
}

CST_COLOR_SPACE_TOKENS: dict[str, str] = {
    "aces_ap1": "ACES_AP1_COLORSPACE",
    "aces (ap1)": "ACES_AP1_COLORSPACE",
    # Camera aliases below must be live render-proofed in DaVinci Resolve before
    # they are added. Unknown DaVinci Resolve tokens can still be passed explicitly via
    # the raw *_COLORSPACE passthrough and will be guarded by cst-set render proof.
    "dji_d_gamut": "DJI_DGAMUT_COLORSPACE",
    "dji d-gamut": "DJI_DGAMUT_COLORSPACE",
    "d_gamut": "DJI_DGAMUT_COLORSPACE",
    "d-gamut": "DJI_DGAMUT_COLORSPACE",
    "red_wide_gamut_rgb": "RED_WIDE_GAMUT_RGB_COLORSPACE",
    "red wide gamut rgb": "RED_WIDE_GAMUT_RGB_COLORSPACE",
    "redwidegamutrgb": "RED_WIDE_GAMUT_RGB_COLORSPACE",
    "sony_s_gamut": "SGAMUT_COLORSPACE",
    "sony s-gamut": "SGAMUT_COLORSPACE",
    "s_gamut": "SGAMUT_COLORSPACE",
    "s-gamut": "SGAMUT_COLORSPACE",
    "sgamut": "SGAMUT_COLORSPACE",
    "sony_s_gamut3": "SGAMUT3_COLORSPACE",
    "sony s-gamut3": "SGAMUT3_COLORSPACE",
    "s_gamut3": "SGAMUT3_COLORSPACE",
    "s-gamut3": "SGAMUT3_COLORSPACE",
    "sgamut3": "SGAMUT3_COLORSPACE",
    "sony_sgamut3cine": "SGAMUT3CINE_COLORSPACE",
    "sony_s_gamut3_cine": "SGAMUT3CINE_COLORSPACE",
    "sony s-gamut3.cine": "SGAMUT3CINE_COLORSPACE",
    "s-gamut3.cine": "SGAMUT3CINE_COLORSPACE",
    "sgamut3cine": "SGAMUT3CINE_COLORSPACE",
    "rec2020": "REC2020_COLORSPACE",
    "rec_2020": "REC2020_COLORSPACE",
    "rec.2020": "REC2020_COLORSPACE",
    "rec 2020": "REC2020_COLORSPACE",
    "bt2020": "REC2020_COLORSPACE",
    "bt.2020": "REC2020_COLORSPACE",
    "rec709": "REC709_COLORSPACE",
    "rec_709": "REC709_COLORSPACE",
    "rec.709": "REC709_COLORSPACE",
    "rec 709": "REC709_COLORSPACE",
    "davinci_wide_gamut": "DAVINCI_WIDE_GAMUT_COLORSPACE",
    "davinci wide gamut": "DAVINCI_WIDE_GAMUT_COLORSPACE",
    "dwg": "DAVINCI_WIDE_GAMUT_COLORSPACE",
}

CST_GAMMA_TOKENS: dict[str, str] = {
    "acescct": "ACESCCT_GAMMA",
    "apple_log": "APPLE_LOG_GAMMA",
    "apple log": "APPLE_LOG_GAMMA",
    "dji_d_log": "DJI_DLOG_GAMMA",
    "dji d-log": "DJI_DLOG_GAMMA",
    "d_log": "DJI_DLOG_GAMMA",
    "d-log": "DJI_DLOG_GAMMA",
    "red_log3g10": "RED_LOG3G10_GAMMA",
    "red log3g10": "RED_LOG3G10_GAMMA",
    "log3g10": "RED_LOG3G10_GAMMA",
    "sony_slog": "SONY_SLOG_GAMMA",
    "sony_s_log": "SONY_SLOG_GAMMA",
    "sony s-log": "SONY_SLOG_GAMMA",
    "s_log": "SONY_SLOG_GAMMA",
    "s-log": "SONY_SLOG_GAMMA",
    "sony_slog2": "SONY_SLOG2_GAMMA",
    "sony_s_log2": "SONY_SLOG2_GAMMA",
    "sony s-log2": "SONY_SLOG2_GAMMA",
    "s_log2": "SONY_SLOG2_GAMMA",
    "s-log2": "SONY_SLOG2_GAMMA",
    "sony_slog3": "SONY_SLOG3_GAMMA",
    "sony_s_log3": "SONY_SLOG3_GAMMA",
    "sony s-log3": "SONY_SLOG3_GAMMA",
    "s-log3": "SONY_SLOG3_GAMMA",
    "davinci_intermediate": "DAVINCI_INTERMEDIATE_GAMMA",
    "davinci intermediate": "DAVINCI_INTERMEDIATE_GAMMA",
    "dwg intermediate": "DAVINCI_INTERMEDIATE_GAMMA",
    "rec709a": "REC709A_GAMMA",
    "rec_709_a": "REC709A_GAMMA",
    "rec.709-a": "REC709A_GAMMA",
    "rec 709-a": "REC709A_GAMMA",
    "gamma24": "TWOPOINTFOUR_GAMMA",
    "gamma_24": "TWOPOINTFOUR_GAMMA",
    "gamma_2_4": "TWOPOINTFOUR_GAMMA",
    "gamma 2.4": "TWOPOINTFOUR_GAMMA",
    "2.4": "TWOPOINTFOUR_GAMMA",
}

CST_COLOR_SPACE_REGISTRY_ALIASES: dict[str, str] = {
    "alexa_wide_gamut": "ALEXA3_COLORSPACE",
    "alexa wide gamut": "ALEXA3_COLORSPACE",
    "arri_wide_gamut_3": "ALEXA3_COLORSPACE",
    "arri wide gamut 3": "ALEXA3_COLORSPACE",
    "arri_wide_gamut_4": "ARRI_LOGC4_COLORSPACE",
    "arri wide gamut 4": "ARRI_LOGC4_COLORSPACE",
    "blackmagic_design_film": "BMDFILM_COLORSPACE",
    "blackmagic design film": "BMDFILM_COLORSPACE",
    "blackmagic_film": "BMDFILM_COLORSPACE",
    "blackmagic film": "BMDFILM_COLORSPACE",
    "bmd_film": "BMDFILM_COLORSPACE",
    "bmd film": "BMDFILM_COLORSPACE",
    "blackmagic_design_video_gen5": "BMDVIDEOV5_COLORSPACE",
    "blackmagic design video gen 5": "BMDVIDEOV5_COLORSPACE",
    "bmd_video_gen5": "BMDVIDEOV5_COLORSPACE",
    "bmd video gen 5": "BMDVIDEOV5_COLORSPACE",
    "canon_cinema_gamut": "CANONLOG2_COLORSPACE",
    "canon cinema gamut": "CANONLOG2_COLORSPACE",
    "canon_log2": "CANONLOG2_COLORSPACE",
    "canon log2": "CANONLOG2_COLORSPACE",
    "d_gamut": "DGAMUT_COLORSPACE",
    "d-gamut": "DGAMUT_COLORSPACE",
    "dji_d_gamut": "DGAMUT_COLORSPACE",
    "dji d-gamut": "DGAMUT_COLORSPACE",
    "davinci_wide_gamut": "DWG_COLORSPACE",
    "davinci wide gamut": "DWG_COLORSPACE",
    "dwg": "DWG_COLORSPACE",
    "f_gamut": "FGAMUT_C_COLORSPACE",
    "f-gamut": "FGAMUT_C_COLORSPACE",
    "f_gamut_c": "FGAMUT_C_COLORSPACE",
    "f-gamut c": "FGAMUT_C_COLORSPACE",
    "fuji_f_gamut": "FGAMUT_C_COLORSPACE",
    "fuji f-gamut": "FGAMUT_C_COLORSPACE",
    "fujifilm_f_gamut": "FGAMUT_C_COLORSPACE",
    "fujifilm f-gamut": "FGAMUT_C_COLORSPACE",
    "panasonic_v_gamut": "VLOG_COLORSPACE",
    "panasonic v-gamut": "VLOG_COLORSPACE",
    "v_gamut": "VLOG_COLORSPACE",
    "v-gamut": "VLOG_COLORSPACE",
    "red_wide_gamut_rgb": "RWG_COLORSPACE",
    "red wide gamut rgb": "RWG_COLORSPACE",
    "redwidegamutrgb": "RWG_COLORSPACE",
}

CST_GAMMA_REGISTRY_ALIASES: dict[str, str] = {
    "alexa_logc": "LOGC_EI800_GAMMA",
    "alexa logc": "LOGC_EI800_GAMMA",
    "arri_logc": "LOGC_EI800_GAMMA",
    "arri logc": "LOGC_EI800_GAMMA",
    "arri_logc3": "LOGC_EI800_GAMMA",
    "arri logc3": "LOGC_EI800_GAMMA",
    "logc3": "LOGC_EI800_GAMMA",
    "arri_logc4": "LOGC4_EI800_GAMMA",
    "arri logc4": "LOGC4_EI800_GAMMA",
    "logc4": "LOGC4_EI800_GAMMA",
    "blackmagic_design_film_gen5": "BMDFILMV5_GAMMA",
    "blackmagic design film gen 5": "BMDFILMV5_GAMMA",
    "blackmagic film gen 5": "BMDFILMV5_GAMMA",
    "bmd film gen 5": "BMDFILMV5_GAMMA",
    "blackmagic_design_video_gen5": "BMDVIDEOV5_GAMMA",
    "blackmagic design video gen 5": "BMDVIDEOV5_GAMMA",
    "bmd video gen 5": "BMDVIDEOV5_GAMMA",
    "canon_c_log": "CANONLOG_GAMMA",
    "canon c-log": "CANONLOG_GAMMA",
    "canon_clog": "CANONLOG_GAMMA",
    "canon clog": "CANONLOG_GAMMA",
    "canon_c_log2": "CANONLOG2_GAMMA",
    "canon c-log2": "CANONLOG2_GAMMA",
    "canon_clog2": "CANONLOG2_GAMMA",
    "canon clog2": "CANONLOG2_GAMMA",
    "canon_c_log3": "CANONLOG3_GAMMA",
    "canon c-log3": "CANONLOG3_GAMMA",
    "canon_clog3": "CANONLOG3_GAMMA",
    "canon clog3": "CANONLOG3_GAMMA",
    "davinci_intermediate": "DAV_INTER_OETF_GAMMA",
    "davinci intermediate": "DAV_INTER_OETF_GAMMA",
    "dwg intermediate": "DAV_INTER_OETF_GAMMA",
    "f_log": "FLOG_OETF_GAMMA",
    "f-log": "FLOG_OETF_GAMMA",
    "fuji_f_log": "FLOG_OETF_GAMMA",
    "fuji f-log": "FLOG_OETF_GAMMA",
    "fujifilm_f_log": "FLOG_OETF_GAMMA",
    "fujifilm f-log": "FLOG_OETF_GAMMA",
    "f_log2": "FLOG2_OETF_GAMMA",
    "f-log2": "FLOG2_OETF_GAMMA",
    "fuji_f_log2": "FLOG2_OETF_GAMMA",
    "fuji f-log2": "FLOG2_OETF_GAMMA",
    "fujifilm_f_log2": "FLOG2_OETF_GAMMA",
    "fujifilm f-log2": "FLOG2_OETF_GAMMA",
    "panasonic_v_log": "PANASONIC_VLOG_GAMMA",
    "panasonic v-log": "PANASONIC_VLOG_GAMMA",
    "v_log": "PANASONIC_VLOG_GAMMA",
    "v-log": "PANASONIC_VLOG_GAMMA",
    "rec709a": "REC709_APPLE_GAMMA",
    "rec_709_a": "REC709_APPLE_GAMMA",
    "rec.709-a": "REC709_APPLE_GAMMA",
    "rec 709-a": "REC709_APPLE_GAMMA",
}



__all__ = [name for name in globals() if name.isupper()]
