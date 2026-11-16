from __future__ import annotations

import random
import time
from collections.abc import Callable
from datetime import UTC, datetime

import httpx


class TwitchAPIError(RuntimeError):
    """A safe-to-display Twitch API error that never includes credentials."""


class TwitchClient:
    TOKEN_URL = "https://id.twitch.tv/oauth2/token"
    HELIX_URL = "https://api.twitch.tv/helix"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
        wall_clock: Callable[[], float] = time.time,
        max_retries: int = 3,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.http = http or httpx.Client(
            timeout=httpx.Timeout(15.0, connect=5.0),
            headers={"User-Agent": "ViralClip-Radar/0.1 (prospective public clip metadata)"},
        )
        self._owns_http = http is None
        self.sleep = sleep
        self.jitter = jitter
        self.wall_clock = wall_clock
        self.max_retries = max_retries
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._rate_limit_reset_at = 0.0

    def close(self) -> None:
        if self._owns_http:
            self.http.close()

    def _get_token(self, force: bool = False) -> str:
        if not force and self._token and self.wall_clock() < self._token_expires_at - 60:
            return self._token
        for attempt in range(self.max_retries + 1):
            try:
                response = self.http.post(
                    self.TOKEN_URL,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "grant_type": "client_credentials",
                    },
                )
            except httpx.RequestError as exc:
                if attempt >= self.max_retries:
                    raise TwitchAPIError(
                        "Could not reach Twitch OAuth endpoint after retries"
                    ) from exc
                self.sleep(self._retry_delay(None, attempt))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt >= self.max_retries:
                    raise TwitchAPIError(
                        f"Twitch OAuth returned HTTP {response.status_code} after retries"
                    )
                self.sleep(self._retry_delay(response, attempt))
                continue
            if response.status_code != 200:
                raise TwitchAPIError(
                    f"Twitch OAuth rejected the configured credentials (HTTP {response.status_code})"
                )
            break
        else:
            raise TwitchAPIError("Twitch OAuth request failed after retries")
        payload = response.json()
        self._token = payload["access_token"]
        self._token_expires_at = self.wall_clock() + int(payload.get("expires_in", 0))
        return self._token

    def _retry_delay(self, response: httpx.Response | None, attempt: int) -> float:
        if response is not None and response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            reset = response.headers.get("Ratelimit-Reset")
            if retry_after:
                try:
                    return max(0.0, float(retry_after))
                except ValueError:
                    pass
            if reset:
                try:
                    return max(0.0, float(reset) - self.wall_clock())
                except ValueError:
                    pass
        return min(30.0, 2**attempt) + self.jitter(0.0, 0.25)

    def _get(self, path: str, params: dict | list[tuple[str, str]]) -> dict:
        token = self._get_token()
        refreshed = False
        retry = 0
        while True:
            remaining = max(0.0, self._rate_limit_reset_at - self.wall_clock())
            if remaining:
                self.sleep(remaining)
            try:
                response = self.http.get(
                    f"{self.HELIX_URL}/{path}",
                    params=params,
                    headers={"Client-Id": self.client_id, "Authorization": f"Bearer {token}"},
                )
            except httpx.RequestError as exc:
                if retry >= self.max_retries:
                    raise TwitchAPIError("Twitch API network request failed after retries") from exc
                self.sleep(self._retry_delay(None, retry))
                retry += 1
                continue

            remaining_header = response.headers.get("Ratelimit-Remaining")
            reset_header = response.headers.get("Ratelimit-Reset")
            if remaining_header == "0" and reset_header:
                try:
                    self._rate_limit_reset_at = float(reset_header)
                except ValueError:
                    pass
            if response.status_code == 401 and not refreshed:
                token = self._get_token(force=True)
                refreshed = True
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if retry >= self.max_retries:
                    raise TwitchAPIError(
                        f"Twitch API returned HTTP {response.status_code} after retries"
                    )
                self.sleep(self._retry_delay(response, retry))
                retry += 1
                continue
            if response.status_code >= 400:
                raise TwitchAPIError(f"Twitch API request failed with HTTP {response.status_code}")
            try:
                return response.json()
            except ValueError as exc:
                raise TwitchAPIError("Twitch API returned invalid JSON") from exc

    def search_categories(self, name: str) -> list[dict]:
        payload = self._get("search/categories", {"query": name, "first": "100"})
        categories = payload.get("data", [])
        if not isinstance(categories, list):
            raise TwitchAPIError("Twitch returned an invalid category list")
        return categories

    def get_clips(
        self,
        *,
        game_id: str | None = None,
        clip_ids: list[str] | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        after: str | None = None,
    ) -> dict:
        if (game_id is None) == (clip_ids is None):
            raise ValueError("provide exactly one of game_id or clip_ids")
        params: list[tuple[str, str]] = []
        if game_id is not None:
            params.extend((("game_id", game_id), ("first", "100")))
            if started_at is not None:
                params.append(
                    (
                        "started_at",
                        started_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                    )
                )
            if ended_at is not None:
                params.append(
                    (
                        "ended_at",
                        ended_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                    )
                )
            if after:
                params.append(("after", after))
        else:
            if not clip_ids or len(clip_ids) > 100:
                raise ValueError("clip ID batches must contain between 1 and 100 IDs")
            params.extend(("id", clip_id) for clip_id in clip_ids)
        return self._get("clips", params)
