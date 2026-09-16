from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

from app.config import Settings


class ArkModelClient:
    """OpenAI-compatible client for both Doubao Vision and DeepSeek endpoints."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("请先安装 openai 依赖") from exc
            if not self.settings.ark_api_key:
                raise RuntimeError("缺少 ARK_API_KEY")
            self._client = OpenAI(
                api_key=self.settings.ark_api_key,
                base_url=self.settings.ark_base_url,
                timeout=self.settings.api_timeout_seconds,
            )
        return self._client

    def analyze_image(self, image_path: str | Path, prompt: str) -> str:
        model = self.settings.vision_model
        if not model:
            raise RuntimeError("缺少 ARK_VISION_MODEL")
        path = Path(image_path)
        mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        image_data = base64.b64encode(path.read_bytes()).decode("ascii")
        response = self._get_client().chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_data}"
                            },
                        },
                    ],
                }
            ],
            temperature=0,
            max_tokens=2048,
        )
        return _message_text(response)

    def analyze_text(self, text: str, prompt: str) -> str:
        model = self.settings.deepseek_model
        if not model:
            raise RuntimeError("缺少 ARK_DEEPSEEK_MODEL")
        response = self._get_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是合同敏感信息识别助手。"},
                {"role": "user", "content": f"{prompt}\n\n合同文本：\n{text}"},
            ],
            temperature=0,
            max_tokens=2048,
        )
        return _message_text(response)


def _message_text(response: Any) -> str:
    content = response.choices[0].message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item) for item in content
        )
    return str(content or "")
