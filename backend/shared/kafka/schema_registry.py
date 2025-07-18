"""Schema registry client utilities."""

from __future__ import annotations

import json
from typing import Any, Dict, cast

import requests  # type: ignore[import-untyped]


class SchemaRegistryClient:
    """Simple client for interacting with a schema registry."""

    def __init__(self, url: str) -> None:
        """Initialize the client with the registry ``url``."""
        self._url = url.rstrip("/")

    def register(self, subject: str, schema: Dict[str, Any]) -> None:
        """Register ``schema`` for ``subject``."""
        payload = {"schema": json.dumps(schema)}
        response = requests.post(
            f"{self._url}/subjects/{subject}/versions",
            json=payload,
            timeout=5,
        )
        response.raise_for_status()

    def fetch(self, subject: str) -> Dict[str, Any]:
        """Retrieve latest schema for ``subject``."""
        response = requests.get(
            f"{self._url}/subjects/{subject}/versions/latest/schema",
            timeout=5,
        )
        response.raise_for_status()
        return cast(Dict[str, Any], json.loads(response.text))
