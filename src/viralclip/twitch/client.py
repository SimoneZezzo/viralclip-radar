from __future__ import annotations

import random
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import isfinite

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
        events: Callable[[dict[str, object]], None] | None = None,
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
        self._events = events
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._rate_limit_reset_at = 0.0
        self._validated_at = float("-inf")

    def close(self) -> None:
        if self._owns_http:
            self.http.close()

    def _event(self, event: str, endpoint: str, **fields: object) -> None:
        if self._events is not None:
            try:
                self._events({"event": event, "endpoint": endpoint, **fields})
            except Exception:  # noqa: BLE001
                # Telemetry must never replace an HTTP result or prevent a retry.
                return

    @staticmethod
    def _network_reason(error: httpx.RequestError) -> str:
        return "timeout" if isinstance(error, httpx.TimeoutException) else "network_error"

    def _request(
        self,
        endpoint: str,
        attempt: int,
        send: Callable[..., httpx.Response],
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        if self._events is None:
            return send(url, **kwargs)
        started = time.perf_counter()
        try:
            response = send(url, **kwargs)
        except httpx.RequestError as exc:
            self._event(
                "http_request",
                endpoint,
                attempt=attempt,
                status=None,
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                outcome=self._network_reason(exc),
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        fields: dict[str, object] = {}
        invalid_headers = []
        for header, field in (
            ("Ratelimit-Remaining", "rate_limit_remaining"),
            ("Ratelimit-Reset", "rate_limit_reset_epoch"),
        ):
            value = response.headers.get(header)
            if value is None:
                continue
            if len(value) <= 16 and value.isascii() and value.isdecimal():
                fields[field] = int(value)
            else:
                invalid_headers.append(field)
        if invalid_headers:
            fields["invalid_rate_limit_headers"] = invalid_headers
        self._event(
            "http_request",
            endpoint,
            attempt=attempt,
            status=response.status_code,
            duration_ms=duration_ms,
            outcome="rate_limited" if response.status_code == 429 else "response",
            **fields,
        )
        return response

    def _wait_for_retry(
        self,
        endpoint: str,
        next_attempt: int,
        backoff_attempt: int,
        reason: str,
        response: httpx.Response | None = None,
    ) -> None:
        delay = self._retry_delay(response, backoff_attempt)
        fields = {"delay_seconds": delay} if isfinite(delay) else {}
        self._event("http_retry", endpoint, attempt=next_attempt, reason=reason, **fields)
        if reason == "http_429":
            self._event("rate_limit_wait", endpoint, reason=reason, **fields)
        self.sleep(delay)

    def _get_token(self, force: bool = False) -> str:
        if not force and self._token and self.wall_clock() < self._token_expires_at - 60:
            return self._token
        reason = "unauthorized" if force else ("expiry" if self._token else "initial")
        self._event("oauth_refresh", "oauth_token", outcome="attempt", reason=reason)
        try:
            token = self._request_token()
        except TwitchAPIError:
            self._event("oauth_refresh", "oauth_token", outcome="failure", reason=reason)
            raise
        self._event("oauth_refresh", "oauth_token", outcome="success", reason=reason)
        return token

    def _request_token(self) -> str:
        endpoint = "oauth_token"
        for attempt in range(self.max_retries + 1):
            try:
                response = self._request(
                    endpoint,
                    attempt + 1,
                    self.http.post,
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
                self._wait_for_retry(endpoint, attempt + 2, attempt, self._network_reason(exc))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt >= self.max_retries:
                    raise TwitchAPIError(
                        f"Twitch OAuth returned HTTP {response.status_code} after retries"
                    )
                reason = "http_429" if response.status_code == 429 else "http_5xx"
                self._wait_for_retry(endpoint, attempt + 2, attempt, reason, response)
                continue
            if response.status_code != 200:
                raise TwitchAPIError(
                    f"Twitch OAuth rejected the configured credentials (HTTP {response.status_code})"
                )
            break
        else:
            raise TwitchAPIError("Twitch OAuth request failed after retries")
        try:
            payload = response.json()
            token = payload["access_token"]
            expires = payload["expires_in"]
            if not isinstance(token, str) or not token or type(expires) is not int or expires <= 0:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise TwitchAPIError("Twitch OAuth returned an invalid token response") from None
        self._token = token
        self._token_expires_at = self.wall_clock() + expires
        self._validated_at = float("-inf")
        return self._token

    def _validate_token(self, token: str) -> None:
        if self.wall_clock() - self._validated_at < 3600:
            return
        endpoint = "oauth_validate"
        for attempt in range(self.max_retries + 1):
            try:
                response = self._request(
                    endpoint,
                    attempt + 1,
                    self.http.get,
                    "https://id.twitch.tv/oauth2/validate",
                    headers={"Authorization": f"OAuth {token}"},
                )
            except httpx.RequestError as exc:
                if attempt == self.max_retries:
                    raise TwitchAPIError("Twitch token validation network failure") from None
                self._wait_for_retry(endpoint, attempt + 2, attempt, self._network_reason(exc))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == self.max_retries:
                    raise TwitchAPIError("Twitch token validation failed after retries")
                reason = "http_429" if response.status_code == 429 else "http_5xx"
                self._wait_for_retry(endpoint, attempt + 2, attempt, reason, response)
                continue
            if response.status_code != 200:
                self._token = None
                raise TwitchAPIError("Twitch token validation rejected the token")
            try:
                payload = response.json()
                if payload["client_id"] != self.client_id:
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                raise TwitchAPIError("Twitch returned invalid token validation data") from None
            self._validated_at = self.wall_clock()
            return

    def _retry_delay(self, response: httpx.Response | None, attempt: int) -> float:
        if response is not None and response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            reset = response.headers.get("Ratelimit-Reset")
            waits = [min(30.0, 2**attempt) + self.jitter(0.0, 0.25)]
            if retry_after:
                try:
                    waits.append(float(retry_after))
                except ValueError:
                    try:
                        waits.append(
                            parsedate_to_datetime(retry_after).timestamp() - self.wall_clock()
                        )
                    except (ValueError, TypeError, OverflowError):
                        pass
            if reset:
                try:
                    waits.append(float(reset) - self.wall_clock())
                except ValueError:
                    pass
            return max(waits)
        return min(30.0, 2**attempt) + self.jitter(0.0, 0.25)

    def _get(self, path: str, params: dict | list[tuple[str, str]], *, endpoint: str) -> dict:
        token = self._get_token()
        self._validate_token(token)
        refreshed = False
        retry = 0
        attempt = 0
        while True:
            remaining = max(0.0, self._rate_limit_reset_at - self.wall_clock())
            if remaining:
                fields = {"delay_seconds": remaining} if isfinite(remaining) else {}
                self._event("rate_limit_wait", endpoint, reason="bucket_exhausted", **fields)
                self.sleep(remaining)
            attempt += 1
            try:
                response = self._request(
                    endpoint,
                    attempt,
                    self.http.get,
                    f"{self.HELIX_URL}/{path}",
                    params=params,
                    headers={"Client-Id": self.client_id, "Authorization": f"Bearer {token}"},
                )
            except httpx.RequestError as exc:
                if retry >= self.max_retries:
                    raise TwitchAPIError("Twitch API network request failed after retries") from exc
                self._wait_for_retry(endpoint, attempt + 1, retry, self._network_reason(exc))
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
                self._validate_token(token)
                self._event("http_retry", endpoint, attempt=attempt + 1, reason="unauthorized")
                refreshed = True
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if retry >= self.max_retries:
                    raise TwitchAPIError(
                        f"Twitch API returned HTTP {response.status_code} after retries"
                    )
                reason = "http_429" if response.status_code == 429 else "http_5xx"
                self._wait_for_retry(endpoint, attempt + 1, retry, reason, response)
                retry += 1
                continue
            if response.status_code >= 400:
                raise TwitchAPIError(f"Twitch API request failed with HTTP {response.status_code}")
            try:
                payload = response.json()
                if not isinstance(payload, dict):
                    raise TypeError
                return payload
            except (ValueError, TypeError) as exc:
                raise TwitchAPIError("Twitch API returned invalid JSON") from exc

    def search_categories(self, name: str) -> list[dict]:
        categories = []
        cursor = None
        for _ in range(10):
            params = {"query": name, "first": "100"}
            if cursor:
                params["after"] = cursor
            payload = self._get("search/categories", params, endpoint="category_search")
            page = self.parse_data(payload)
            if any(
                not isinstance(item.get("name"), str)
                or not isinstance(item.get("id"), str)
                or not item["id"]
                for item in page
            ):
                raise TwitchAPIError("Twitch returned invalid category fields")
            categories.extend(page)
            if any(item["name"].casefold() == name.casefold() for item in page):
                return categories
            cursor = self.parse_cursor(payload)
            if not cursor:
                return categories
        raise TwitchAPIError("Category search safety cap reached; use an explicit category ID")

    @staticmethod
    def parse_data(payload: dict) -> list[dict]:
        data = payload.get("data")
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise TwitchAPIError("Twitch returned an invalid data list")
        return data

    @staticmethod
    def parse_cursor(payload: dict) -> str | None:
        pagination = payload.get("pagination", {})
        if not isinstance(pagination, dict):
            raise TwitchAPIError("Twitch returned invalid pagination")
        cursor = pagination.get("cursor")
        if cursor is not None and not isinstance(cursor, str):
            raise TwitchAPIError("Twitch returned invalid cursor")
        return cursor or None

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
                if started_at.tzinfo is None or started_at.utcoffset() is None:
                    raise ValueError("started_at must be timezone-aware")
                params.append(
                    (
                        "started_at",
                        started_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                    )
                )
            if ended_at is not None:
                if ended_at.tzinfo is None or ended_at.utcoffset() is None:
                    raise ValueError("ended_at must be timezone-aware")
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
        endpoint = "clip_discovery" if game_id is not None else "clip_refresh"
        return self._get("clips", params, endpoint=endpoint)
