"""Troceado de Markdown por secciones. Cada fragmento conserva la ruta de encabezados para poder citarla."""

import re

from pydantic import BaseModel

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
MAX_CHARS = 1500


class MarkdownChunk(BaseModel):
    section: str | None  # "Sección > Subsección", sin el título del documento
    text: str  # texto a indexar: incluye la ruta de encabezados como contexto


def title_of(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        m = _HEADING.match(line)
        if m and len(m.group(1)) == 1:
            return m.group(2).strip()
    return fallback


def _blocks(body: str) -> list[str]:
    """Párrafos, listas y tablas separados por líneas en blanco (sin partir bloques de código)."""
    blocks, current, in_code = [], [], False
    for line in body.splitlines():
        if _FENCE.match(line):
            in_code = not in_code
        if not line.strip() and not in_code:
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _pack(blocks: list[str]) -> list[str]:
    """Agrupa bloques consecutivos hasta MAX_CHARS; un bloque más largo va solo."""
    out, current = [], ""
    for b in blocks:
        if current and len(current) + len(b) + 2 > MAX_CHARS:
            out.append(current)
            current = b
        else:
            current = f"{current}\n\n{b}" if current else b
    if current:
        out.append(current)
    return out


def chunk_markdown(markdown: str, title: str) -> list[MarkdownChunk]:
    path: list[tuple[int, str]] = []  # (nivel, texto) de los encabezados abiertos, sin el H1
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    in_code = False
    for line in markdown.splitlines():
        if _FENCE.match(line):
            in_code = not in_code
        m = None if in_code else _HEADING.match(line)
        if m:
            level, text = len(m.group(1)), m.group(2).strip()
            if level == 1:
                path = []
                sections.append((None, []))
                continue
            path = [(lvl, t) for lvl, t in path if lvl < level] + [(level, text)]
            sections.append((" > ".join(t for _, t in path), []))
            continue
        sections[-1][1].append(line)

    chunks = []
    for section, lines in sections:
        body = "\n".join(lines).strip()
        if not body:
            continue
        header = f"{title} > {section}" if section else title
        for part in _pack(_blocks(body)):
            chunks.append(MarkdownChunk(section=section, text=f"{header}\n\n{part}"))
    return chunks
