"""Strict semantic canonicalization for Fusion ``.setting`` table values."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..errors import APICallFailed


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str


def _tokens(raw: bytes) -> list[_Token]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise APICallFailed("Fusion composition export is not valid UTF-8.") from exc
    result: list[_Token] = []
    index = 0
    punctuation = "{}[]=,()"
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if text.startswith("--", index):
            long_comment = _long_bracket(text, index + 2)
            if long_comment is not None:
                _, index = long_comment
            else:
                newline = text.find("\n", index + 2)
                index = len(text) if newline < 0 else newline + 1
            continue
        long_string = _long_bracket(text, index)
        if long_string is not None:
            value, index = long_string
            result.append(_Token("string", value))
            continue
        if char in ('"', "'"):
            quote = char
            start = index
            index += 1
            escaped = False
            while index < len(text):
                current = text[index]
                index += 1
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == quote:
                    break
            else:
                raise APICallFailed(
                    "Fusion composition export has an unterminated string."
                )
            result.append(_Token("string", text[start:index]))
            continue
        if char in punctuation:
            result.append(_Token(char, char))
            index += 1
            continue
        start = index
        while (
            index < len(text)
            and not text[index].isspace()
            and text[index] not in punctuation
            and not text.startswith("--", index)
        ):
            index += 1
        if start == index:
            raise APICallFailed(
                "Fusion composition export contains an unsupported token.",
                details={"offset": index},
            )
        result.append(_Token("atom", text[start:index]))
    return result


def _long_bracket(text: str, start: int) -> tuple[str, int] | None:
    """Return a Lua long-bracket token and its exclusive end offset."""

    if start >= len(text) or text[start] != "[":
        return None
    cursor = start + 1
    while cursor < len(text) and text[cursor] == "=":
        cursor += 1
    if cursor >= len(text) or text[cursor] != "[":
        return None
    close = "]" + ("=" * (cursor - start - 1)) + "]"
    end = text.find(close, cursor + 1)
    if end < 0:
        raise APICallFailed(
            "Fusion composition export has an unterminated long-bracket value."
        )
    exclusive_end = end + len(close)
    return text[start:exclusive_end], exclusive_end


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.index = 0

    def _peek(self, kind: str | None = None) -> _Token | None:
        if self.index >= len(self.tokens):
            return None
        token = self.tokens[self.index]
        return token if kind is None or token.kind == kind else None

    def _take(self, kind: str | None = None) -> _Token:
        token = self._peek(kind)
        if token is None:
            actual = self._peek()
            raise APICallFailed(
                "Fusion composition Tools table has invalid syntax.",
                details={
                    "expected": kind,
                    "actual": actual.kind if actual is not None else "end",
                    "token_index": self.index,
                },
            )
        self.index += 1
        return token

    def value(self) -> Any:
        token = self._peek()
        if token is None:
            self._take("value")
        if token.kind == "{":
            value: Any = self.table(ordered=False)
        elif token.kind in {"atom", "string"}:
            self.index += 1
            value = (token.kind, token.value)
        else:
            self._take("value")
        while True:
            if self._peek("(") is not None:
                self._take("(")
                arguments = []
                while self._peek(")") is None:
                    arguments.append(self.value())
                    if self._peek(",") is None:
                        break
                    self._take(",")
                self._take(")")
                value = ("call", value, tuple(arguments))
                continue
            if self._peek("{") is not None:
                ordered = (
                    value == ("call", ("atom", "ordered"), ())
                )
                value = ("constructor", value, self.table(ordered=ordered))
                continue
            return value

    def table(self, *, ordered: bool) -> Any:
        self._take("{")
        positional = []
        keyed = []
        while self._peek("}") is None:
            if self._peek() is None:
                self._take("}")
            if self._peek("[") is not None:
                self._take("[")
                key = self.value()
                self._take("]")
                self._take("=")
                entry = ("keyed", key, self.value())
            elif (
                self._peek() is not None
                and self._peek().kind in {"atom", "string"}
                and self.index + 1 < len(self.tokens)
                and self.tokens[self.index + 1].kind == "="
            ):
                key_token = self._take()
                self._take("=")
                entry = (
                    "keyed",
                    (key_token.kind, key_token.value),
                    self.value(),
                )
            else:
                entry = ("positional", self.value())
            if entry[0] == "keyed":
                keyed.append(entry)
            else:
                positional.append(entry)
            if self._peek(",") is not None:
                self._take(",")
            elif self._peek("}") is None:
                raise APICallFailed(
                    "Fusion composition Tools table has entries without separators.",
                    details={"token_index": self.index},
                )
        self._take("}")
        if ordered:
            # Fusion's ordered() tables preserve insertion order. Mixed positional
            # and keyed entries are not emitted by DaVinci Resolve; reject them
            # instead of inventing a potentially weaker normalization.
            if positional and keyed:
                raise APICallFailed(
                    "Fusion ordered Tools table mixes positional and keyed entries."
                )
            entries = positional or keyed
        else:
            canonical_keys = [_encode(entry[1]) for entry in keyed]
            if len(canonical_keys) != len(set(canonical_keys)):
                raise APICallFailed("Fusion Tools table contains duplicate keys.")
            keyed = [
                entry
                for _, entry in sorted(
                    zip(canonical_keys, keyed), key=lambda pair: pair[0]
                )
            ]
            entries = positional + keyed
        return ("table", ordered, tuple(entries))


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def canonicalize_fusion_tools_value(raw: bytes) -> bytes:
    """Return a complete deterministic representation of one ``Tools`` value.

    Whitespace, comments, trailing commas and field order in ordinary Lua tables
    are non-semantic. Positional entries and every ``ordered()`` table retain
    order. All tokens, constructors, keys and nested values remain represented.
    """

    parser = _Parser(_tokens(raw))
    value = parser.value()
    if parser._peek() is not None:
        raise APICallFailed(
            "Fusion composition Tools value has trailing tokens.",
            details={"token_index": parser.index},
        )
    return _encode(value).encode("utf-8")


def canonicalize_fusion_tools(raw: bytes) -> bytes:
    """Extract and canonicalize the real top-level ``Tools`` field."""

    parser = _Parser(_tokens(raw))
    if (
        parser._peek("atom") is not None
        and parser._peek().value == "Tools"
        and parser.index + 1 < len(parser.tokens)
        and parser.tokens[parser.index + 1].kind == "="
    ):
        parser._take("atom")
        parser._take("=")
        tools = parser.value()
    else:
        document = parser.value()
        if document[0] == "constructor":
            document = document[2]
        if document[0] != "table":
            raise APICallFailed("Fusion composition export has no top-level table.")
        matches = [
            entry[2]
            for entry in document[2]
            if entry[0] == "keyed" and entry[1] == ("atom", "Tools")
        ]
        if len(matches) != 1:
            raise APICallFailed(
                "Fusion composition export must have exactly one top-level Tools field.",
                details={"match_count": len(matches)},
            )
        tools = matches[0]
    if parser._peek() is not None:
        raise APICallFailed(
            "Fusion composition export has trailing tokens.",
            details={"token_index": parser.index},
        )
    return _encode(tools).encode("utf-8")
