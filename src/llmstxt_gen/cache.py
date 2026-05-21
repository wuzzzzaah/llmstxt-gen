"""Caching utilities for incremental generation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from llmstxt_gen.parsers.base import (
    ParsedClass,
    ParsedConstant,
    ParsedFunction,
    ParsedModule,
    ParsedParameter,
    ParsedRoute,
)


def get_sha256(content: str) -> str:
    """Return the SHA256 hash of the given content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_cache(path: Path) -> dict[str, Any]:
    """Load the cache from a JSON file. Return an empty dict if not found or invalid."""
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return cast(dict[str, Any], json.load(f))
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(path: Path, data: dict[str, Any]) -> None:
    """Save the cache data to a JSON file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def serialize_module(module: ParsedModule) -> dict[str, Any]:
    """Convert a ParsedModule to a dictionary for JSON serialization."""
    return asdict(module)


def deserialize_module(data: dict[str, Any]) -> ParsedModule:
    """Convert a dictionary back into a ParsedModule instance."""

    def _make_fn(f_data: dict[str, Any]) -> ParsedFunction:
        return ParsedFunction(
            name=f_data["name"],
            parameters=[ParsedParameter(**p) for p in f_data.get("parameters", [])],
            return_type=f_data.get("return_type", ""),
            docstring=f_data.get("docstring", ""),
            line=f_data.get("line", 0),
            is_async=f_data.get("is_async", False),
            is_private=f_data.get("is_private", False),
            is_property=f_data.get("is_property", False),
            decorators=f_data.get("decorators", []),
            _heads_count=f_data.get("_heads_count", 1),
        )

    functions = [_make_fn(f) for f in data.get("functions", [])]

    classes = [
        ParsedClass(
            name=c["name"],
            docstring=c.get("docstring", ""),
            bases=c.get("bases", []),
            methods=[_make_fn(m) for m in c.get("methods", [])],
            class_vars=[ParsedConstant(**cv) for cv in c.get("class_vars", [])],
            line=c.get("line", 0),
        )
        for c in data.get("classes", [])
    ]

    constants = [ParsedConstant(**c) for c in data.get("constants", [])]
    routes = [ParsedRoute(**r) for r in data.get("routes", [])]

    return ParsedModule(
        name=data["name"],
        path=data["path"],
        language=data["language"],
        docstring=data.get("docstring", ""),
        functions=functions,
        classes=classes,
        constants=constants,
        routes=routes,
        imports=data.get("imports", []),
        env_vars=data.get("env_vars", {}),
    )
