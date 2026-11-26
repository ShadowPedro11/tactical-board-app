"""Read one UTF-8 match URL from stdin and write a desktop JSON response."""

import json
import os
from pathlib import Path
import ssl
import sys


if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from match_api import match_response  # noqa: E402


def main():
    # A frozen OpenSSL build may point to a certificate file on the build machine.
    if getattr(sys, "frozen", False) and sys.platform != "win32":
        if not ssl.get_default_verify_paths().cafile:
            import certifi

            os.environ.setdefault("SSL_CERT_FILE", certifi.where())

    # The importer accepts at most 2,048 characters, each up to four UTF-8 bytes.
    raw = sys.stdin.buffer.read(8193)
    try:
        url = raw.decode("utf-8")
    except UnicodeDecodeError:
        url = None
    status, body = match_response(url)
    envelope = json.dumps({"status": status, "body": body}, ensure_ascii=False, allow_nan=False)
    sys.stdout.buffer.write((envelope + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
