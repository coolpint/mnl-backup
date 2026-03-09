from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Dict, Optional


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)


@dataclass
class HttpResponse:
    requested_url: str
    final_url: str
    status_code: int
    headers: Dict[str, str]
    content: bytes

    def text(self, encoding: Optional[str] = None) -> str:
        content_type = self.headers.get("content-type", "")
        if encoding is None and "charset=" in content_type:
            encoding = content_type.split("charset=", 1)[1].split(";")[0].strip()
        if not encoding:
            encoding = "utf-8"
        return self.content.decode(encoding, errors="replace")


class HttpClient:
    def __init__(self, timeout: float = 30.0, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self.timeout = timeout
        self.user_agent = user_agent

    def fetch(self, url: str) -> HttpResponse:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept-Language": "ko,en-US;q=0.9,en;q=0.8",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                headers = {key.lower(): value for key, value in response.headers.items()}
                return HttpResponse(
                    requested_url=url,
                    final_url=response.geturl(),
                    status_code=response.getcode() or 200,
                    headers=headers,
                    content=response.read(),
                )
        except urllib.error.HTTPError as exc:
            headers = {key.lower(): value for key, value in exc.headers.items()}
            return HttpResponse(
                requested_url=url,
                final_url=exc.geturl(),
                status_code=exc.code,
                headers=headers,
                content=exc.read(),
            )

