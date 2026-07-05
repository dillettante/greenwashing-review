from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _coerce(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.lower() in {"true", "yes"}:
        return True
    if value.lower() in {"false", "no"}:
        return False
    if value.lower() in {"null", "none"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        return [_coerce(item) for item in value[1:-1].split(",") if item.strip()]
    try:
        return int(value)
    except ValueError:
        return value


def load_context(path: Path) -> dict[str, Any]:
    """JSON 또는 단순한 1단계 YAML key:value 파일을 읽는다."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("context는 객체여야 합니다")
        return data
    except json.JSONDecodeError:
        data: dict[str, Any] = {}
        for line_no, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#") or line == "---":
                continue
            if ":" not in line:
                raise ValueError(f"context.yaml {line_no}행: key: value 형식이 아닙니다")
            key, value = line.split(":", 1)
            data[key.strip()] = _coerce(value)
        return data


REQUIRED_CONTEXT_FIELDS = (
    "company",
    "product",
    "published_date",
    "medium",
    "audience",
)


def context_warnings(context: dict[str, Any]) -> list[str]:
    return [f"[확인 필요] context.yaml의 {key} 값" for key in REQUIRED_CONTEXT_FIELDS if not context.get(key)]

