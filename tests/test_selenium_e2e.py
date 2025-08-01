"""End-to-end tests for ``SeleniumFallback``."""

from __future__ import annotations

from pathlib import Path
import asyncio
import sys
from types import SimpleNamespace
import yaml
import pytest


class _Options:
    def add_argument(self, arg: str) -> None:
        pass


sys.modules.setdefault(
    "selenium.webdriver.firefox.options",
    SimpleNamespace(Options=_Options),
)

from marketplace_publisher.clients import SeleniumFallback
from marketplace_publisher import rules
from marketplace_publisher.db import Marketplace
import selenium.webdriver


@pytest.fixture(autouse=True)
def _enable_selenium(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use the real Firefox driver for these tests."""
    monkeypatch.delenv("SELENIUM_SKIP", raising=False)
    monkeypatch.setattr(
        "selenium.webdriver.Firefox",
        selenium.webdriver.Firefox,
        raising=False,
    )


def _write_rules(tmp_path: Path, page: Path, bad: bool = False) -> Path:
    """Return rules file path with selectors for the test page."""
    selectors = {
        "url": page.as_uri(),
        "upload_input": "#upload" if not bad else "#missing",
        "title_input": "#title",
        "submit_button": "#submit",
    }
    data = {
        "redbubble": {
            "max_file_size_mb": 10,
            "max_width": 8000,
            "max_height": 8000,
            "upload_limit": 50,
            "selectors": selectors,
        }
    }
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def _write_page(tmp_path: Path) -> Path:
    """Write a simple HTML page used by tests and return its path."""
    page = tmp_path / "page.html"
    page.write_text(
        """
        <html>
        <body>
        <input type='file' id='upload'/>
        <input type='text' id='title'/>
        <button id='submit' onclick="this.setAttribute('data-clicked','1')">Submit</button>
        </body>
        </html>
        """,
        encoding="utf-8",
    )
    return page


@pytest.mark.asyncio()
async def test_selenium_publish_success(tmp_path: Path) -> None:
    """Publishing with valid selectors should not create screenshots."""
    page = _write_page(tmp_path)
    rules_path = _write_rules(tmp_path, page)
    rules.load_rules(rules_path)
    design = tmp_path / "design.png"
    design.write_text("img")
    fallback = SeleniumFallback(screenshot_dir=tmp_path)
    await fallback.publish(Marketplace.redbubble, design, {"title": "t"})
    assert not list(tmp_path.glob("*.png"))


@pytest.mark.asyncio()
async def test_selenium_publish_failure_with_screenshot(tmp_path: Path) -> None:
    """Failures should store a screenshot in the specified directory."""
    page = _write_page(tmp_path)
    rules_path = _write_rules(tmp_path, page, bad=True)
    rules.load_rules(rules_path)
    design = tmp_path / "design.png"
    design.write_text("img")
    fallback = SeleniumFallback(screenshot_dir=tmp_path)
    with pytest.raises(Exception):
        await fallback.publish(Marketplace.redbubble, design, {"title": "t"})
    assert list(tmp_path.glob("*.png"))
    assert list(tmp_path.glob("*.log"))


@pytest.mark.asyncio()
async def test_selenium_publish_waits_async(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ensure publish yields control using ``asyncio.sleep`` for retries."""
    page = _write_page(tmp_path)
    rules_path = _write_rules(tmp_path, page, bad=True)
    rules.load_rules(rules_path)
    design = tmp_path / "design.png"
    design.write_text("img")
    fallback = SeleniumFallback(screenshot_dir=tmp_path)

    class DummyDriver:
        def get(self, url: str) -> None:
            pass

        def find_element(self, *args: str, **kwargs: str) -> None:
            raise Exception("fail")

        def save_screenshot(self, path: str) -> None:
            pass

        def get_log(self, name: str) -> list[str]:
            return []

    fallback.driver = DummyDriver()

    event = asyncio.Event()
    original_sleep = asyncio.sleep

    async def fake_sleep(seconds: float) -> None:
        await original_sleep(0)
        event.set()

    monkeypatch.setattr(
        "marketplace_publisher.clients.asyncio.sleep",
        fake_sleep,
    )
    with pytest.raises(Exception):
        await fallback.publish(
            Marketplace.redbubble,
            design,
            {"title": "t"},
            max_attempts=2,
        )
    assert event.is_set()
