"""Events source adapter."""

from __future__ import annotations

from typing import Any

from .base import BaseAdapter
from ..settings import settings


class EventsAdapter(BaseAdapter):
    """Adapter for public holiday events API."""

    def __init__(
        self,
        base_url: str | None = None,
        proxies: list[str] | None = None,
        rate_limit: int = 5,
        country_code: str | None = None,
        fetch_limit: int | None = None,
    ) -> None:
        """Initialize adapter with optional ``base_url``."""
        self.country_code = country_code or settings.events_country_code
        self.fetch_limit = fetch_limit or settings.events_fetch_limit
        super().__init__(base_url or "https://date.nager.at", proxies, rate_limit)

    async def fetch(self) -> list[dict[str, Any]]:
        """Return upcoming public holidays."""
        resp = await self._request(f"/api/v3/NextPublicHolidays/{self.country_code}")
        if resp is None:
            return []
        data = resp.json()[: self.fetch_limit]
        return data
