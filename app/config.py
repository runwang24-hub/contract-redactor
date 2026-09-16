from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


@dataclass(frozen=True, slots=True)
class Settings:
    mediakit_api_key: str
    ocr_endpoint: str
    ocr_upload_endpoint: str
    ocr_tool_version: str
    ocr_task_type: str
    ark_api_key: str
    ark_base_url: str
    vision_model: str
    deepseek_model: str
    api_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        # dotenv is optional so the clients can also be configured by the shell.
        try:
            from dotenv import load_dotenv

            project_root = Path(__file__).resolve().parents[1]
            load_dotenv(project_root / ".env")
        except ImportError:
            pass

        return cls(
            mediakit_api_key=_first_env("MEDIAKIT_API_KEY"),
            ocr_endpoint=_first_env(
                "MEDIAKIT_OCR_ENDPOINT",
                default="https://mediakit.cn-beijing.volces.com/api/v1/tools-sync/image-ocr",
            ),
            ocr_upload_endpoint=_first_env(
                "MEDIAKIT_UPLOAD_ENDPOINT",
                default="https://mediakit.cn-beijing.volces.com/api/v1/tools-sync/request-media-upload-url",
            ),
            ocr_tool_version=_first_env("MEDIAKIT_OCR_TOOL_VERSION", default="standard"),
            ocr_task_type=_first_env("MEDIAKIT_OCR_TASK_TYPE", default="spotting"),
            ark_api_key=_first_env("ARK_API_KEY"),
            ark_base_url=_first_env(
                "ARK_BASE_URL", default="https://ark.cn-beijing.volces.com/api/v3"
            ),
            vision_model=_first_env("ARK_VISION_MODEL"),
            deepseek_model=_first_env("ARK_DEEPSEEK_MODEL"),
            api_timeout_seconds=float(_first_env("API_TIMEOUT_SECONDS", default="120")),
        )

    def require_ocr_credentials(self) -> None:
        if not self.mediakit_api_key:
            raise RuntimeError("缺少 OCR 配置：MEDIAKIT_API_KEY")

    def require_ark_credentials(self) -> None:
        missing = []
        if not self.ark_api_key:
            missing.append("ARK_API_KEY")
        if not self.vision_model:
            missing.append("ARK_VISION_MODEL")
        if not self.deepseek_model:
            missing.append("ARK_DEEPSEEK_MODEL")
        if missing:
            raise RuntimeError("缺少方舟配置：" + ", ".join(missing))
