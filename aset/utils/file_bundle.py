from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


FILE_START_RE = re.compile(r"^---FILE_START\s+(.+?)---\s*$")
FILE_END_RE = re.compile(r"^---FILE_END\s+(.+?)---\s*$")


@dataclass
class FileBundle:
    files: Dict[str, str]  # path -> content


class FileBundleParseError(ValueError):
    pass


def parse_file_bundle(text: str) -> FileBundle:
    """
    Parses output in the format:

    ---FILE_MAP_START---
    path1
    path2
    ---FILE_MAP_END---

    ---FILE_START path1---
    ...
    ---FILE_END path1---
    ...

    We don't strictly require the FILE_MAP section (models sometimes omit it),
    but we do require FILE_START/FILE_END blocks.
    """
    lines = text.splitlines()

    files: Dict[str, List[str]] = {}
    current_path: str | None = None
    current_buf: List[str] = []

    def flush_current() -> None:
        nonlocal current_path, current_buf
        if current_path is not None:
            files[current_path] = current_buf
        current_path = None
        current_buf = []

    for i, line in enumerate(lines):
        m_start = FILE_START_RE.match(line)
        if m_start:
            if current_path is not None:
                raise FileBundleParseError(f"Nested FILE_START at line {i+1}")
            current_path = m_start.group(1).strip()
            current_buf = []
            continue

        m_end = FILE_END_RE.match(line)
        if m_end:
            end_path = m_end.group(1).strip()
            if current_path is None:
                raise FileBundleParseError(f"FILE_END without FILE_START at line {i+1}")
            if end_path != current_path:
                raise FileBundleParseError(
                    f"Mismatched FILE_END at line {i+1}: got {end_path}, expected {current_path}"
                )
            flush_current()
            continue

        if current_path is not None:
            current_buf.append(line)

    if current_path is not None:
        raise FileBundleParseError(f"Unclosed FILE_START for {current_path}")

    if not files:
        raise FileBundleParseError("No files found. LLM output may not follow file bundle format.")

    joined = {p: "\n".join(buf).rstrip() + "\n" for p, buf in files.items()}
    return FileBundle(files=joined)


def write_file_bundle(bundle: FileBundle, out_dir: Path) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for rel_path, content in bundle.files.items():
        # Normalize paths
        rel_path = rel_path.lstrip("/").replace("\\", "/")
        target = out_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(target)
    return written
