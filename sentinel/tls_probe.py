"""Standalone fixed TLS probe. Never runs input as code or as shell text."""

import json
import socket
import ssl
import sys


def main() -> None:
    address, port, hostname = sys.argv[1:]
    try:
        with socket.create_connection((address, int(port)), timeout=5) as raw:
            with ssl.create_default_context().wrap_socket(raw, server_hostname=hostname) as sock:
                cert = sock.getpeercert()
                result = {
                    "ok": True,
                    "version": sock.version(),
                    "cipher": sock.cipher()[0],
                    "expires": cert.get("notAfter"),
                    "subject": cert.get("subject"),
                    "issuer": cert.get("issuer"),
                }
    except (OSError, ValueError) as exc:
        result = {
            "ok": False,
            "error_type": type(exc).__name__,
            "note": "TLS 連線或信任鏈驗證未成功，不能僅據此斷定網站有漏洞。",
        }
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
