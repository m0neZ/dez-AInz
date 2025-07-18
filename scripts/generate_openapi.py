#!/usr/bin/env python3
"""Generate OpenAPI specs for microservices."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Iterable

from openapi_schema_validator import OAS30Validator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("KAFKA_SKIP", "1")
os.environ.setdefault("SELENIUM_SKIP", "1")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///openapi.db")
os.environ.setdefault("ABTEST_DB_URL", "sqlite:///abtest.db")

DOCS_OPENAPI_DIR = PROJECT_ROOT / "docs" / "openapi"
DOCS_INDEX = PROJECT_ROOT / "docs" / "openapi_specs.rst"


def discover_main_files(base: Path) -> Iterable[Path]:
    """Yield all FastAPI ``main.py`` files."""
    return base.glob("backend/*/**/main.py")


def ensure_doc(service: str) -> None:
    """Create minimal RST page for ``service`` if missing."""
    DOCS_OPENAPI_DIR.mkdir(exist_ok=True)
    doc_path = DOCS_OPENAPI_DIR / f"{service}.rst"
    if not doc_path.exists():
        title = f"{service.replace('-', ' ').title()} API"
        doc_path.write_text(
            f"{title}\n{'=' * len(title)}\n\n.. openapi:: ../../openapi/{service}.json\n   :encoding: utf-8\n",
            encoding="utf-8",
        )

    if DOCS_INDEX.exists():
        lines = DOCS_INDEX.read_text(encoding="utf-8").splitlines()
    else:
        lines = ["OpenAPI Specifications", "======================", "", ".. toctree::", "   :maxdepth: 1", ""]

    entry = f"   openapi/{service}"
    if entry not in lines:
        lines.append(entry)
        DOCS_INDEX.write_text("\n".join(lines) + "\n", encoding="utf-8")

OPENAPI_DIR = PROJECT_ROOT / "openapi"
OPENAPI_DIR.mkdir(exist_ok=True)


def generate_from_file(main_file: Path) -> None:
    """Load FastAPI ``app`` from ``main_file`` and write its spec."""
    service = main_file.parts[1]
    service_root = PROJECT_ROOT / "backend" / service
    src_dir = service_root / "src"
    if src_dir.exists():
        sys.path.insert(0, str(src_dir))
    else:
        sys.path.insert(0, str(service_root))

    package_dir = main_file.parent
    package = package_dir.name if (package_dir / "__init__.py").exists() else ""
    module_name = f"{package}.main" if package else "main"
    spec_obj = importlib.util.spec_from_file_location(module_name, main_file)
    module = importlib.util.module_from_spec(spec_obj)
    if package and package not in sys.modules:
        pkg_spec = importlib.machinery.ModuleSpec(package, loader=None)
        pkg = importlib.util.module_from_spec(pkg_spec)
        pkg.__path__ = [str(package_dir)]
        sys.modules[package] = pkg
    sys.modules[module_name] = module
    assert spec_obj.loader is not None
    spec_obj.loader.exec_module(module)
    app = getattr(module, "app", None)
    if not app or not hasattr(app, "openapi"):
        return
    data = app.openapi()
    OAS30Validator.check_schema(data)
    path = OPENAPI_DIR / f"{service}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    ensure_doc(service)


for main_file in discover_main_files(PROJECT_ROOT):
    generate_from_file(main_file)

# scoring-engine manual spec
sys.path.insert(0, str(PROJECT_ROOT / "backend" / "scoring-engine"))
try:
    from scoring_engine.app import ScoreRequest, WeightsUpdate
except Exception as exc:  # pragma: no cover - runtime import guard
    raise SystemExit(f"Failed importing scoring_engine: {exc}")

spec = {
    "openapi": "3.0.2",
    "info": {"title": "Scoring Engine", "version": "1.0.0"},
    "paths": {
        "/weights": {
            "get": {"responses": {"200": {"description": "OK"}}},
            "put": {
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/WeightsUpdate"}
                        }
                    },
                    "required": True,
                },
                "responses": {"200": {"description": "OK"}},
            },
        },
        "/score": {
            "post": {
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ScoreRequest"}
                        }
                    },
                    "required": True,
                },
                "responses": {"200": {"description": "OK"}},
            }
        },
        "/centroid/{source}": {
            "get": {
                "parameters": [
                    {
                        "name": "source",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {"200": {"description": "OK"}},
            }
        },
        "/health": {"get": {"responses": {"200": {"description": "OK"}}}},
        "/ready": {"get": {"responses": {"200": {"description": "Ready"}}}},
        "/metrics": {"get": {"responses": {"200": {"description": "OK"}}}},
    },
    "components": {
        "schemas": {
            "WeightsUpdate": WeightsUpdate.model_json_schema(),
            "ScoreRequest": ScoreRequest.model_json_schema(),
        }
    },
}
(OPENAPI_DIR / "scoring-engine.json").write_text(
    json.dumps(spec, indent=2), encoding="utf-8"
)
OAS30Validator.check_schema(spec)
ensure_doc("scoring-engine")


