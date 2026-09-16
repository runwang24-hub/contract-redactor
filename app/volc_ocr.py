from __future__ import annotations

import mimetypes
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests

from app.config import Settings


@dataclass(slots=True)
class OCRLine:
    text: str
    bbox: dict[str, Any] | None = None
    polygon: Any = None
    confidence: float | None = None
    chars: list[dict[str, Any]] | None = None


@dataclass(slots=True)
class OCRResult:
    text: str
    lines: list[OCRLine]
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "lines": [asdict(line) for line in self.lines],
            "raw": self.raw,
        }


class MediaKitOCRClient:
    """Client for the AI MediaKit synchronous image OCR API.

    Local files are uploaded through MediaKit's temporary upload URL first. The
    OCR API then receives the returned ``mediakit://...`` file identifier.
    """

    MAX_OCR_IMAGE_BYTES = 10 * 1024 * 1024

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()

    def recognize_file(
        self,
        image_path: str | Path,
        *,
        tool_version: str | None = None,
        task_type: str | None = None,
        keywords: list[str] | None = None,
    ) -> OCRResult:
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.stat().st_size > self.MAX_OCR_IMAGE_BYTES:
            raise ValueError("OCR 单张图片不能超过 10 MB")

        file_url = self._upload_file(path)
        return self.recognize_url(
            file_url,
            tool_version=tool_version,
            task_type=task_type,
            keywords=keywords,
        )

    def recognize_url(
        self,
        image_url: str,
        *,
        tool_version: str | None = None,
        task_type: str | None = None,
        keywords: list[str] | None = None,
    ) -> OCRResult:
        self.settings.require_ocr_credentials()
        selected_version = tool_version or self.settings.ocr_tool_version
        selected_task_type = task_type or self.settings.ocr_task_type
        payload: dict[str, Any] = {
            "image_url": image_url,
            "tool_version": selected_version,
            "task_type": selected_task_type,
        }
        if selected_task_type == "keyword":
            if selected_version != "max":
                raise ValueError("keyword 模式要求 tool_version=max")
            if not keywords:
                raise ValueError("keyword 模式必须提供 keywords")
            payload["keywords"] = keywords
            payload["max_keywords"] = len(keywords)

        response = requests.post(
            self.settings.ocr_endpoint,
            json=payload,
            headers=self._auth_headers(),
            timeout=self.settings.api_timeout_seconds,
        )
        self._raise_for_response(response, "OCR")
        return self._normalize(response.json())

    def _upload_file(self, path: Path) -> str:
        self.settings.require_ocr_credentials()
        response = requests.post(
            self.settings.ocr_upload_endpoint,
            json={},
            headers=self._auth_headers(),
            timeout=self.settings.api_timeout_seconds,
        )
        self._raise_for_response(response, "申请 MediaKit 上传地址")
        payload = response.json()
        result = payload.get("result") or {}
        if not isinstance(result, dict):
            raise RuntimeError("申请 MediaKit 上传地址返回了无效结果")

        file_id = result.get("file_id")
        upload_url = result.get("upload_url")
        upload_headers = result.get("upload_headers") or {}
        if not file_id or not upload_url:
            raise RuntimeError(f"申请 MediaKit 上传地址缺少 file_id/upload_url：{payload}")
        # The API currently returns either an empty list or an object here,
        # depending on whether the signed upload URL needs extra headers.
        if upload_headers == []:
            upload_headers = {}
        if not isinstance(upload_headers, dict):
            raise RuntimeError("MediaKit 上传地址返回了无效的 upload_headers")

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        headers = {str(key): str(value) for key, value in upload_headers.items()}
        headers.setdefault("Content-Type", content_type)
        with path.open("rb") as file_handle:
            upload_response = requests.put(
                upload_url,
                data=file_handle,
                headers=headers,
                timeout=self.settings.api_timeout_seconds,
            )
        self._raise_for_response(upload_response, "上传图片")
        return str(file_id)

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.mediakit_api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _raise_for_response(response: requests.Response, operation: str) -> None:
        if response.ok:
            return
        detail = response.text[:2000]
        raise RuntimeError(f"{operation}请求失败 HTTP {response.status_code}: {detail}")

    @staticmethod
    def _normalize(payload: dict[str, Any]) -> OCRResult:
        if payload.get("success") is False:
            raise RuntimeError(f"MediaKit OCR 返回失败：{payload}")
        result = payload.get("result") or {}
        if not isinstance(result, dict):
            result = {}

        lines: list[OCRLine] = []
        ocr_items = result.get("ocr_result") or []
        if not isinstance(ocr_items, list):
            ocr_items = []
        for item in ocr_items:
            if not isinstance(item, dict):
                continue
            lines.append(
                OCRLine(
                    text=str(item.get("content", "")),
                    bbox=_bbox_from_item(item),
                    confidence=_as_float(item.get("confidence")),
                )
            )
        return OCRResult(
            text="\n".join(line.text for line in lines),
            lines=lines,
            raw=payload,
        )


# Keep the existing import name stable while the project migrates to MediaKit.
VolcengineOCRClient = MediaKitOCRClient


def _bbox_from_item(item: dict[str, Any]) -> dict[str, Any] | None:
    keys = ("top_left_x", "top_left_y", "bottom_right_x", "bottom_right_y")
    if not any(key in item for key in keys):
        return None
    return {key: item.get(key) for key in keys}


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
