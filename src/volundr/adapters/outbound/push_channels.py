"""Outbound NotificationChannel adapters for session attention pushes.

Selected via the dynamic-adapter config (``push.adapter`` + ``kwargs``):

- ``LoggingNotificationChannel`` — default; logs only, no external calls.
- ``WebhookNotificationChannel`` — POSTs the push to a relay URL (the relay
  owns device fan-out). HTTP/1.1, no extra dependencies.
- ``ApnsNotificationChannel`` — direct Apple Push, token-based (JWT) auth.
  APNs only speaks HTTP/2, so httpx needs ``h2`` (the ``httpx[http2]`` extra).
- ``CredentialStoreApnsNotificationChannel`` — the same, with the signing key
  (team id, key id, .p8) read from the credential store (OpenBao on the
  clusters) instead of process configuration.

A device registered with an ``environment`` ("sandbox" for development builds,
"production" for TestFlight/App Store) is pushed through that APNs host; one
without uses the channel's default (``use_sandbox``).

Each channel has two entry points, and both raise ``NotificationDeliveryError``
when nothing was delivered. ``send`` is what the needs-input attention push
uses (the session service runs it detached and reports a failure); ``deliver``
is what the notification outbox uses (through ``PushNotificationSink``) and also
describes what was delivered, so the outbox can retry or give up honestly.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

from niuu.adapters.notifications.delivery_http import (
    is_retryable_status,
    redact_url,
    status_failure,
    transport_failure,
)
from niuu.ports.notifications import NotificationDeliveryError
from volundr.domain.models import DevicePlatform, DeviceToken, PushMessage
from volundr.domain.ports import NotificationChannel

logger = logging.getLogger(__name__)


class LoggingNotificationChannel(NotificationChannel):
    """No-op channel that records what WOULD be pushed. Safe default."""

    async def send(self, message: PushMessage, devices: list[DeviceToken]) -> None:
        logger.info(
            "Push (logging): owner=%s kind=%s session=%s devices=%d title=%r",
            message.owner_id,
            message.kind,
            message.session_id,
            len(devices),
            message.title,
        )


class WebhookNotificationChannel(NotificationChannel):
    """POST the push as JSON to a relay URL, optionally HMAC-signed.

    The relay (a push gateway) is responsible for resolving the owner's devices
    and delivering to APNs/FCM/web-push, so this channel does not require
    registered device tokens.
    """

    def __init__(
        self,
        *,
        url: str,
        secret: str = "",
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ):
        self._url = url
        self._secret = secret
        self._timeout = timeout_seconds
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def send(self, message: PushMessage, devices: list[DeviceToken]) -> None:
        await self.deliver(message, devices)

    async def deliver(self, message: PushMessage, devices: list[DeviceToken]) -> str:
        if not self._url:
            raise NotificationDeliveryError("Push relay has no url configured", retryable=False)
        payload: dict[str, Any] = {
            "type": message.event_type,
            "owner_id": message.owner_id,
            "session_id": message.session_id,
            "kind": message.kind,
            "title": message.title,
            "body": message.body,
            "urgency": message.urgency,
            "request_id": message.request_id,
            "device_tokens": [{"platform": d.platform.value, "token": d.token} for d in devices],
        }
        if message.notification_id:
            payload["notification_id"] = message.notification_id
        if message.url:
            payload["url"] = message.url
        headers = {"content-type": "application/json"}
        if self._secret:
            body = httpx.Request("POST", self._url, json=payload).content
            signature = hmac.new(self._secret.encode(), body, hashlib.sha256).hexdigest()
            headers["X-Niuu-Signature"] = f"sha256={signature}"
        target = f"push relay {redact_url(self._url)}"
        client = await self._get_client()
        try:
            resp = await client.post(self._url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise transport_failure(exc, target) from None
        if resp.status_code >= httpx.codes.BAD_REQUEST:
            raise status_failure(target, resp)
        return f"{target} accepted HTTP {resp.status_code}"


class ApnsNotificationChannel(NotificationChannel):
    """Direct Apple Push Notification service channel (token-based auth).

    Signs a short-lived ES256 JWT (PyJWT + cryptography) with the .p8 key and
    delivers one request per iOS device over HTTP/2. Pushes use the
    ``time-sensitive`` interruption level so the alert and Live Activity / widget
    surface even under Focus.
    """

    _PROD_HOST = "https://api.push.apple.com"
    _SANDBOX_HOST = "https://api.sandbox.push.apple.com"

    def __init__(
        self,
        *,
        team_id: str,
        key_id: str,
        private_key: str,
        bundle_id: str,
        use_sandbox: bool = False,
        token_ttl_seconds: int = 3000,
        client: httpx.AsyncClient | None = None,
    ):
        self._team_id = team_id
        self._key_id = key_id
        self._private_key = private_key
        self._bundle_id = bundle_id
        self._host = self._SANDBOX_HOST if use_sandbox else self._PROD_HOST
        self._token_ttl = token_ttl_seconds
        self._client = client
        self._jwt_cache: str | None = None
        self._jwt_issued_at: float = 0.0

    def _auth_token(self) -> str:
        """Return a cached/fresh provider JWT (Apple allows reuse < 1h)."""
        import jwt  # PyJWT — local import keeps module import light

        now = time.time()
        if self._jwt_cache and (now - self._jwt_issued_at) < self._token_ttl:
            return self._jwt_cache
        token = jwt.encode(
            {"iss": self._team_id, "iat": int(now)},
            self._private_key,
            algorithm="ES256",
            headers={"kid": self._key_id},
        )
        self._jwt_cache = token
        self._jwt_issued_at = now
        return token

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            # HTTP/2 is mandatory for APNs; requires the `h2` package at deploy time.
            self._client = httpx.AsyncClient(http2=True, timeout=10.0)
        return self._client

    async def send(self, message: PushMessage, devices: list[DeviceToken]) -> None:
        # An owner without iOS devices has nothing for APNs to deliver to.
        if not any(d.platform is DevicePlatform.IOS for d in devices):
            return
        await self.deliver(message, devices)

    async def deliver(self, message: PushMessage, devices: list[DeviceToken]) -> str:
        ios_devices = [d for d in devices if d.platform is DevicePlatform.IOS]
        if not ios_devices:
            raise NotificationDeliveryError(
                "The owner has no registered iOS devices", retryable=False
            )
        try:
            auth = self._auth_token()
            client = await self._get_client()
        except Exception as exc:
            raise NotificationDeliveryError(
                f"APNs auth/client setup failed: {type(exc).__name__}", retryable=False
            ) from None

        payload: dict[str, Any] = {
            "aps": {
                "alert": {"title": message.title, "body": message.body},
                "sound": "default",
                "interruption-level": "time-sensitive",
            },
            "session_id": message.session_id,
            "kind": message.kind,
            "request_id": message.request_id,
        }
        if message.notification_id:
            payload["notification_id"] = message.notification_id
        if message.url:
            payload["url"] = message.url
        accepted = 0
        failures: list[NotificationDeliveryError] = []
        for device in ios_devices:
            error = await self._post(client, auth, device, payload, message.owner_id)
            if error is None:
                accepted += 1
                continue
            failures.append(error)
        if accepted:
            return f"APNs accepted {accepted} of {len(ios_devices)} devices"
        raise NotificationDeliveryError(
            f"APNs delivered to none of {len(ios_devices)} devices: {failures[0]}",
            retryable=any(failure.retryable for failure in failures),
            retry_after=max(
                (f.retry_after for f in failures if f.retry_after is not None), default=None
            ),
        )

    def _host_for(self, device: DeviceToken) -> str:
        """The APNs host for the device's token environment (the default when unknown)."""
        if device.environment == "sandbox":
            return self._SANDBOX_HOST
        if device.environment == "production":
            return self._PROD_HOST
        return self._host

    async def _post(
        self,
        client: httpx.AsyncClient,
        auth: str,
        device: DeviceToken,
        payload: dict[str, Any],
        owner_id: str,
    ) -> NotificationDeliveryError | None:
        topic = device.app_bundle_id or self._bundle_id
        try:
            resp = await client.post(
                f"{self._host_for(device)}/3/device/{device.token}",
                json=payload,
                headers={
                    "authorization": f"bearer {auth}",
                    "apns-topic": topic,
                    "apns-push-type": "alert",
                    "apns-priority": "10",
                },
            )
        except Exception as exc:
            # One device's failure must not stop delivery to the others.
            logger.warning("APNs delivery failed for owner %s: %s", owner_id, type(exc).__name__)
            return NotificationDeliveryError(
                f"{type(exc).__name__} while contacting APNs", retryable=True
            )
        if resp.status_code >= httpx.codes.BAD_REQUEST:
            logger.warning(
                "APNs rejected push (status=%d) for owner %s", resp.status_code, owner_id
            )
            return NotificationDeliveryError(
                f"APNs returned HTTP {resp.status_code}",
                retryable=is_retryable_status(resp.status_code),
                status_code=resp.status_code,
            )
        return None


class CredentialStoreApnsNotificationChannel(NotificationChannel):
    """APNs with each tenant's signing key kept in the credential store.

    The key is a credential like any other integration secret: a tenant admin stores
    it once as a tenant credential (``POST /api/v1/credentials/tenant``, name
    ``apns``) with the fields ``team_id``, ``key_id`` and ``private_key`` (the whole
    .p8, PEM header included), and optionally ``bundle_id`` and ``use_sandbox``
    ("true"/"false"). Every device carries the tenant its owner registered it in, so
    no tenant is configured here: each device is pushed with its own tenant's key.

    The key is read before each delivery, so a rotated key applies without a restart,
    and a missing one fails the delivery with a clear reason instead of stopping
    Volundr from starting.
    """

    def __init__(
        self,
        *,
        credential_store: Any = None,
        credential_name: str = "apns",
        bundle_id: str = "",
        use_sandbox: bool = False,
        token_ttl_seconds: int = 3000,
        client: httpx.AsyncClient | None = None,
    ):
        if credential_store is None:
            raise ValueError("CredentialStoreApnsNotificationChannel needs a credential store")
        self._credential_store = credential_store
        self._credential_name = credential_name
        self._bundle_id = bundle_id
        self._use_sandbox = use_sandbox
        self._token_ttl = token_ttl_seconds
        self._client = client
        # tenant → (key material, channel): a channel keeps its provider JWT until the key changes.
        self._channels: dict[str, tuple[tuple[str, ...], ApnsNotificationChannel]] = {}

    async def send(self, message: PushMessage, devices: list[DeviceToken]) -> None:
        if not any(d.platform is DevicePlatform.IOS for d in devices):
            return
        await self.deliver(message, devices)

    async def deliver(self, message: PushMessage, devices: list[DeviceToken]) -> str:
        ios_devices = [d for d in devices if d.platform is DevicePlatform.IOS]
        if not ios_devices:
            raise NotificationDeliveryError(
                "The owner has no registered iOS devices", retryable=False
            )
        by_tenant: dict[str, list[DeviceToken]] = {}
        for device in ios_devices:
            by_tenant.setdefault(device.tenant_id or "", []).append(device)

        accepted: list[str] = []
        failures: list[NotificationDeliveryError] = []
        for tenant, group in by_tenant.items():
            try:
                channel = await self._channel_for(tenant)
                accepted.append(await channel.deliver(message, group))
            except NotificationDeliveryError as error:
                failures.append(error)
        if accepted:
            return "; ".join(accepted)
        raise NotificationDeliveryError(
            str(failures[0]),
            retryable=any(failure.retryable for failure in failures),
            retry_after=max(
                (f.retry_after for f in failures if f.retry_after is not None), default=None
            ),
        )

    async def _channel_for(self, tenant: str) -> ApnsNotificationChannel:
        """The APNs channel signed with ``tenant``'s key from the credential store."""
        if not tenant:
            raise NotificationDeliveryError(
                "The device was registered without a tenant; register it again to push it",
                retryable=False,
            )
        data = await self._credential_store.get_value("tenant", tenant, self._credential_name)
        if not data:
            raise NotificationDeliveryError(
                f"Tenant {tenant} has no APNs key credential {self._credential_name!r} "
                "in the credential store",
                retryable=False,
            )
        team_id = str(data.get("team_id", "")).strip()
        key_id = str(data.get("key_id", "")).strip()
        private_key = str(data.get("private_key", "")).strip()
        if not (team_id and key_id and private_key):
            raise NotificationDeliveryError(
                f"Tenant {tenant}'s APNs key credential {self._credential_name!r} needs "
                "team_id, key_id and private_key",
                retryable=False,
            )
        bundle_id = str(data.get("bundle_id", "")).strip() or self._bundle_id
        use_sandbox = self._use_sandbox
        if "use_sandbox" in data:
            use_sandbox = str(data["use_sandbox"]).strip().lower() in {"1", "true", "yes"}
        material = (team_id, key_id, private_key, bundle_id, str(use_sandbox))
        cached = self._channels.get(tenant)
        if cached is not None and cached[0] == material:
            return cached[1]
        channel = ApnsNotificationChannel(
            team_id=team_id,
            key_id=key_id,
            private_key=private_key,
            bundle_id=bundle_id,
            use_sandbox=use_sandbox,
            token_ttl_seconds=self._token_ttl,
            client=await self._shared_client(),
        )
        self._channels[tenant] = (material, channel)
        return channel

    async def _shared_client(self) -> httpx.AsyncClient:
        if self._client is None:
            # HTTP/2 is mandatory for APNs (the httpx[http2] extra installs h2).
            self._client = httpx.AsyncClient(http2=True, timeout=10.0)
        return self._client
