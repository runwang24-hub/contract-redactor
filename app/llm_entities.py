from __future__ import annotations

import json
import re
from typing import Any

from app.ark_client import ArkModelClient
from app.entities import Entity


ENTITY_PROMPT = """
你是合同脱敏助手。请从下面的 OCR 文本中找出需要用黑框完全遮盖的敏感信息。

需要识别的类型包括：
- PERSON：自然人姓名、当事人、联系人、律师、法官等
- ORG_COMPANY：公司、企业、机构、律所等完整名称
- ADDRESS：详细住址、办公地址、收货地址
- PHONE：手机和固定电话
- ID_CARD：身份证号或其他个人证件号
- EMAIL：电子邮箱
- BANK_CARD：银行卡号
- BANK_ACCOUNT：银行账号
- PLATE：车牌号
- IP：IP 地址
- BUSINESS_SECRET：商业秘密、账号密码、密钥等

只返回 JSON 数组，不要 Markdown，不要解释。格式如下：
[{"text":"原文中的完整敏感信息","label":"PERSON"}]

要求：
1. text 必须逐字摘录自原文，不要改写，不要补全。
2. 公司名称请返回完整名称，程序会用坐标把完整公司名遮盖。
3. 不要识别普通日期、金额、案号、法律条款编号和公开机构名称。
4. 如果没有敏感信息，返回 []。
""".strip()


class DeepSeekEntityDetector:
    """Use DeepSeek to find semantic entities in one OCR page."""

    def __init__(self, client: ArkModelClient | None = None) -> None:
        self.client = client or ArkModelClient()

    def detect(self, text: str) -> list[Entity]:
        if not text.strip():
            return []
        response_text = self.client.analyze_text(text, ENTITY_PROMPT)
        items = _parse_json_items(response_text)
        entities: list[Entity] = []
        for item in items:
            value = str(item.get("text", "")).strip()
            label = str(item.get("label", "")).strip().upper()
            if not value or not label:
                continue
            # A person/company can be repeated on the same page. The model
            # usually returns the value once, so cover every exact occurrence.
            for match in re.finditer(re.escape(value), text):
                entities.append(
                    Entity(
                        start=match.start(),
                        end=match.end(),
                        label=label,
                        text=value,
                        source="deepseek",
                        score=0.9,
                    )
                )
        return entities


def _parse_json_items(response_text: str) -> list[dict[str, Any]]:
    """Accept a clean JSON array or a JSON array wrapped in model text."""
    cleaned = response_text.strip()
    candidates = [cleaned]
    left = cleaned.find("[")
    right = cleaned.rfind("]")
    if left >= 0 and right > left:
        candidates.append(cleaned[left : right + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payload = payload.get("entities", [])
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]
    return []
