from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request

from .config import OPENAI_API_KEY


RESPONSES_URL = "https://api.openai.com/v1/responses"


class OpenAIJsonProvider:
    provider_name = "openai"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else OPENAI_API_KEY

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def generate_json(
        self,
        *,
        model: str,
        content: list[dict],
        schema_name: str,
        schema: dict,
        timeout: int = 45,
    ) -> dict:
        if not self.api_key:
            raise RuntimeError("未配置 OPENAI_API_KEY")

        request_payload = {
            "model": model,
            "input": [{"role": "user", "content": content}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        response = self._post_json(request_payload, timeout=timeout)
        result_text = response.get("output_text") or _extract_output_text(response)
        if not result_text:
            raise RuntimeError("OpenAI 没有返回可解析结果")

        try:
            return json.loads(result_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenAI 返回结果不是有效 JSON") from exc

    def _post_json(self, payload: dict, *, timeout: int) -> dict:
        request = urllib.request.Request(
            RESPONSES_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout,
                context=_ssl_context(),
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API 调用失败: {message}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("无法连接 OpenAI API，请检查网络") from exc


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def _extract_output_text(response: dict) -> str | None:
    for output in response.get("output", []):
        for content in output.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return content["text"]
    return None
