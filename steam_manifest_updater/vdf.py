"""A small, dependency-free reader for Valve's text KeyValues (VDF/ACF)."""
from __future__ import annotations


class VDFError(ValueError):
    """Invalid or unsupported text VDF."""


def _tokens(data: str):
    i = 0
    while i < len(data):
        ch = data[i]
        if ch.isspace() or ch == '\ufeff':
            i += 1
            continue
        if data.startswith('//', i):
            newline = data.find('\n', i)
            i = len(data) if newline == -1 else newline + 1
            continue
        if ch in '{}':
            yield ch
            i += 1
            continue
        if ch == '"':
            i += 1
            parts = []
            while i < len(data):
                ch = data[i]
                if ch == '"':
                    i += 1
                    break
                if ch == '\\' and i + 1 < len(data) and data[i + 1] in ('\\', '"'):
                    parts.append(data[i + 1])
                    i += 2
                else:
                    parts.append(ch)
                    i += 1
            else:
                raise VDFError('Unterminated quoted string')
            yield ''.join(parts)
            continue
        start = i
        while i < len(data) and not data[i].isspace() and data[i] not in '{}':
            if data.startswith('//', i):
                break
            i += 1
        if i == start:
            raise VDFError(f'Unexpected character at index {i}')
        yield data[start:i]


def parse(data: str) -> dict:
    """Parse nested, text-based VDF. No binary-VDF or conditional directives."""
    items = list(_tokens(data))
    pos = 0

    def mapping(nested: bool) -> dict:
        nonlocal pos
        result = {}
        while pos < len(items):
            key = items[pos]
            pos += 1
            if key == '}':
                if not nested:
                    raise VDFError('Unexpected closing brace')
                return result
            if key == '{':
                raise VDFError('Expected a key, got an opening brace')
            if pos >= len(items):
                raise VDFError(f'Missing value for key {key!r}')
            value = items[pos]
            pos += 1
            if value == '{':
                value = mapping(True)
            elif value == '}':
                raise VDFError(f'Missing value for key {key!r}')
            result[key] = value
        if nested:
            raise VDFError('Missing closing brace')
        return result

    return mapping(False)


def get_ci(mapping: dict, key: str, default=None):
    """Steam has used inconsistent key casing in manifests."""
    return next((v for k, v in mapping.items() if k.lower() == key.lower()), default)
