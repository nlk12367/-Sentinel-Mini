"""Single-origin URL validation and bounded HTTP evidence collection."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import socket
import ssl
import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit, urlunsplit

from .contracts import JsonObject, now

NETWORK_ERRORS = (OSError, ValueError, http.client.HTTPException)


@dataclass
class Scope:
    """One explicit origin; resolve once and connect to the approved IPs."""

    url: str
    addresses: list[str] = field(init=False)
    host: str = field(init=False)
    port: int = field(init=False)
    scheme: str = field(init=False)
    path: str = field(init=False)
    authority: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.url, str) or len(self.url) > 2048:
            raise ValueError("目標 URL 不正確。")
        if any(ord(c) < 33 for c in self.url) or "\\" in self.url:
            raise ValueError("URL 不可含空白、控制字元或反斜線。")
        u = urlsplit(self.url)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise ValueError("請輸入完整 http:// 或 https:// URL。")
        if u.username is not None or u.password is not None or u.fragment or u.query:
            raise ValueError("目標 URL 不可含帳密、query 或 fragment；請使用公開測試頁面。")
        port = u.port  # Validate malformed ports before DNS lookup.
        self.host = u.hostname.encode("idna").decode("ascii")
        self.port = port or (443 if u.scheme == "https" else 80)
        if not 1 <= self.port <= 65535:
            raise ValueError("Port 超出範圍。")
        literal = f"[{self.host}]" if ":" in self.host else self.host
        self.url = urlunsplit((u.scheme, f"{literal}:{self.port}", u.path or "/", "", ""))
        self.scheme = u.scheme
        self.path = quote(u.path or "/", safe="/%:@!$&'()*+,;=-._~")
        self.authority = f"{literal}:{self.port}"
        self.addresses = sorted(
            {a[4][0] for a in socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)}
        )
        for address in self.addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_unspecified or ip.is_multicast or ip.is_link_local:
                raise ValueError("不接受 unspecified、multicast 或 link-local 位址。")

    def check(self, url: str) -> None:
        u = urlsplit(url)
        origin = (u.scheme, u.hostname, u.port or (443 if u.scheme == "https" else 80))
        if origin != (self.scheme, self.host, self.port):
            raise ValueError("請求超出指定 origin。")

    def fetch(self) -> JsonObject:
        """GET only, no redirects/proxies/cookies, max 128 KiB, pinned DNS."""
        started = time.monotonic()
        raw = socket.create_connection((self.addresses[0], self.port), timeout=6)
        response = None
        try:
            if self.scheme == "https":
                raw = ssl.create_default_context().wrap_socket(raw, server_hostname=self.host)
            request_headers = {
                "Host": self.authority,
                "User-Agent": "SentinelMini/1.0 (authorized-config-audit)",
                "Accept": "text/html",
                "Accept-Encoding": "identity",
                "Connection": "close",
            }
            request_text = (
                f"GET {self.path} HTTP/1.1\r\n"
                + "".join(f"{key}: {value}\r\n" for key, value in request_headers.items())
                + "\r\n"
            )
            raw.sendall(request_text.encode("ascii"))
            response = http.client.HTTPResponse(raw, method="GET")
            response.begin()
            body = bytearray()
            while len(body) <= 131072:
                remaining = 12 - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError("HTTP 回應超過 12 秒。")
                raw.settimeout(min(6, remaining))
                chunk = response.read1(min(8192, 131073 - len(body)))
                if not chunk:
                    break
                body.extend(chunk)
            headers = []
            for key, value in response.getheaders():
                if key.lower() == "set-cookie":
                    first, sep, rest = value.partition(";")
                    name = first.partition("=")[0]
                    value = name + "=[REDACTED]" + (sep + rest if sep else "")
                elif key.lower() in ("authorization", "proxy-authorization", "www-authenticate"):
                    value = "[REDACTED]"
                headers.append((key, value[:2048]))
            return {
                "id": uuid.uuid4().hex[:12],
                "kind": "http",
                "time": now(),
                "url": self.url,
                "method": "GET",
                "status": response.status,
                "headers": headers,
                "body": bytes(body[:131072]).decode("utf-8", errors="replace"),
                "truncated": len(body) > 131072,
                "body_sha256": hashlib.sha256(body[:131072]).hexdigest(),
                "peer": self.addresses[0],
            }
        finally:
            if response:
                response.close()
            raw.close()
