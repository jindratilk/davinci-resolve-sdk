"""Fusion .setting template rendering and CharacterLevelStyling."""

from __future__ import annotations


def parse_styled_text(text: str, bold_style: str = "ExtraBold") -> tuple[str, str]:
    """
    Parse markdown **bold** markers into Fusion CharacterLevelStyling.
    
    Returns (clean_text, lua_cls_array).
    CLS code 109 = Font Style.
    
    Example:
        >>> parse_styled_text("This is **bold** text", "ExtraBold")
        ("This is bold text", "{ 109, 8, 12, String = \\"ExtraBold\\" }")
    """
    clean_text = ""
    styling_items = []
    parts = text.split("**")
    current_index = 0

    for i, part in enumerate(parts):
        part_len = len(part)
        if i % 2 == 1:
            # Bold section
            start = current_index
            end = current_index + part_len
            lua_entry = f'{{ 109, {start}, {end}, String = "{bold_style}" }}'
            styling_items.append(lua_entry)
        clean_text += part
        current_index += part_len

    lua_array = ",\n\t\t\t\t\t\t\t".join(styling_items)
    return clean_text, lua_array


def escape_lua_string(value: str) -> str:
    """
    Escape string for Lua string literal.
    
    Handles: backslashes, quotes, newlines.
    """
    return (value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


# Default placeholder patterns (can be overridden via config)
DEFAULT_TEXT_PLACEHOLDERS = [
    "PLACEHOLDER_TEXT",
    "TEXT_PLACEHOLDER",
    "__TEXT__",
    "{{PLACEHOLDER_TEXT}}",
    "{{TEXT_PLACEHOLDER}}",
]
DEFAULT_STYLE_PLACEHOLDERS = [
    "PLACEHOLDER_STYLING",
    "STYLING_PLACEHOLDER",
    "__STYLING__",
    "{{PLACEHOLDER_STYLING}}",
    "{{STYLING_PLACEHOLDER}}",
    "{{STYLING_ARRAY_PLACEHOLDER}}",
]
DEFAULT_IMAGE_PLACEHOLDERS = [
    "PLACEHOLDER_IMAGE",
    "IMAGE_PLACEHOLDER",
    "__IMAGE__",
    "{{PLACEHOLDER_IMAGE}}",
    "{{IMAGE_PLACEHOLDER}}",
]


def render_setting_template(
    template: str,
    text: str | None = None,
    styling: str | None = None,
    image: str | None = None,
    replacements: dict[str, str] | None = None,
    text_placeholders: list[str] | None = None,
    style_placeholders: list[str] | None = None,
    image_placeholders: list[str] | None = None,
) -> str:
    """
    Render a Fusion .setting template by replacing placeholders.
    
    Args:
        template: .setting file content (Lua code)
        text: Text to insert (will be Lua-escaped)
        styling: CharacterLevelStyling Lua array
        image: Image path (will be Lua-escaped)
        replacements: Additional raw placeholder replacements
        text_placeholders: Custom text placeholder patterns
        style_placeholders: Custom styling placeholder patterns
        image_placeholders: Custom image placeholder patterns
    
    Returns:
        Rendered .setting file content
    """
    result = template

    text_phs = text_placeholders or DEFAULT_TEXT_PLACEHOLDERS
    style_phs = style_placeholders or DEFAULT_STYLE_PLACEHOLDERS
    image_phs = image_placeholders or DEFAULT_IMAGE_PLACEHOLDERS

    if text is not None:
        escaped = escape_lua_string(text)
        for ph in sorted(text_phs, key=len, reverse=True):
            result = result.replace(ph, escaped)

    if styling is not None:
        for ph in sorted(style_phs, key=len, reverse=True):
            result = result.replace(ph, styling)

    if image is not None:
        escaped_img = escape_lua_string(image)
        for ph in sorted(image_phs, key=len, reverse=True):
            result = result.replace(ph, escaped_img)

    for placeholder, value in (replacements or {}).items():
        if placeholder is None:
            continue
        result = result.replace(str(placeholder), "" if value is None else str(value))

    return result
