from __future__ import annotations

import re

from app.entities import Entity
from app.span import merge_entities


class RuleDetector:
    PHONE_RE = re.compile(
        r"(?<![\d.-])(?:"
        r"1[3-9]\d{9}|"
        r"1[3-9]\d[- .]?\d{4}[- .]?\d{4}|"
        r"0\d{2,3}[- ]?\d{7,8}(?:-\d{1,6})?"
        r")(?![\d.-])"
    )
    EMAIL_RE = re.compile(
        r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@"
        r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])"
    )
    ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
    BANK_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){16,30}(?!\d)")
    IP_RE = re.compile(
        r"(?<!\d)(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}"
        r"(?:25[0-5]|2[0-4]\d|1?\d?\d)(?!\d)"
    )
    URL_RE = re.compile(r"https?://[^\s，。；；、)）]+")
    PLATE_RE = re.compile(r"(?<![A-Z0-9])[\u4e00-\u9fa5][A-Z][·.]?[A-Z0-9]{5,6}(?![A-Z0-9])")
    CASE_NUMBER_RE = re.compile(
        r"[（(]\d{4}[）)]"
        r"[\u4e00-\u9fa5]{1,3}\d{2,6}"
        r"(?:民|刑|行|执|商|知|赔|破|清|再|申|抗|监)"
        r"(?:初|终|再|申|执|特|撤)?\d+号"
    )
    CERTIFICATE_NUMBER_RE = re.compile(
        r"(?:证件号码|证件号|统一社会信用代码|社会信用代码|"
        r"营业执照(?:注册)?号|注册号|纳税人识别号|组织机构代码)"
        r"\s*[:：]?\s*"
        r"(?P<value>[0-9A-Za-z][0-9A-Za-z-]{8,28}[0-9A-Za-z])"
    )
    LABELED_CODE_RE = re.compile(
        r"(?:证件号码|证件号|统一社会信用代码|社会信用代码|"
        r"营业执照(?:注册)?号|纳税人识别号|组织机构代码|"
        r"邮政编码|邮编|注册号|序列号|流水号|"
        r"[\u4e00-\u9fa5A-Za-z]{0,12}(?:编号|代码|卡号|证号|账号|帐号|单号))"
        r"\s*[:：]?\s*"
        r"(?P<value>[0-9A-Za-z\u4e00-\u9fa5（）()【】\[\]·._/#-]{3,80})"
    )
    LONG_CODE_RE = re.compile(
        r"(?<![A-Za-z0-9])"
        r"(?P<value>[A-Za-z0-9][A-Za-z0-9_./-]{6,38}[A-Za-z0-9])"
        r"(?![A-Za-z0-9])"
    )

    def detect(self, text: str) -> list[Entity]:
        entities: list[Entity] = []
        entities.extend(self._find_simple(text, self.PHONE_RE, "PHONE"))
        entities.extend(self._find_simple(text, self.EMAIL_RE, "EMAIL"))
        entities.extend(self._find_id_cards(text))
        entities.extend(self._find_bank_cards(text))
        entities.extend(self._find_simple(text, self.IP_RE, "IP"))
        entities.extend(self._find_simple(text, self.URL_RE, "URL"))
        entities.extend(self._find_simple(text, self.PLATE_RE, "PLATE"))
        entities.extend(self._find_simple(text, self.CASE_NUMBER_RE, "CASE_NUMBER"))
        entities.extend(self._find_certificate_numbers(text))
        entities.extend(self._find_labeled_codes(text))
        entities.extend(self._find_long_codes(text))
        return merge_entities(entities)

    def _find_simple(self, text: str, regex: re.Pattern[str], label: str) -> list[Entity]:
        return [
            Entity(
                start=match.start(),
                end=match.end(),
                label=label,
                text=match.group(0),
                source="rule",
            )
            for match in regex.finditer(text)
        ]

    def _find_id_cards(self, text: str) -> list[Entity]:
        entities = []
        for match in self.ID_CARD_RE.finditer(text):
            entities.append(
                Entity(match.start(), match.end(), "ID_CARD", match.group(0), "rule")
            )
        return entities

    def _find_bank_cards(self, text: str) -> list[Entity]:
        entities = []
        for match in self.BANK_CARD_RE.finditer(text):
            normalized = re.sub(r"\D", "", match.group(0))
            context = text[max(0, match.start() - 8) : match.start()]
            if len(normalized) >= 16 and _luhn_valid(normalized):
                entities.append(
                    Entity(
                        start=match.start(),
                        end=match.end(),
                        label="BANK_CARD",
                        text=match.group(0),
                        source="rule",
                        metadata={"normalized": normalized},
                    )
                )
            elif len(normalized) >= 8 and any(word in context for word in ("账号", "账户", "卡号", "银行卡")):
                entities.append(
                    Entity(
                        start=match.start(),
                        end=match.end(),
                        label="BANK_ACCOUNT",
                        text=match.group(0),
                        source="rule",
                        metadata={"normalized": normalized},
                    )
                )
        return entities

    def _find_certificate_numbers(self, text: str) -> list[Entity]:
        entities = []
        for match in self.CERTIFICATE_NUMBER_RE.finditer(text):
            value = match.group("value")
            entities.append(
                Entity(
                    start=match.start("value"),
                    end=match.end("value"),
                    label="CERTIFICATE_NUMBER",
                    text=value,
                    source="rule",
                )
            )
        return entities

    def _find_labeled_codes(self, text: str) -> list[Entity]:
        entities = []
        for match in self.LABELED_CODE_RE.finditer(text):
            value = match.group("value")
            if not any(char.isdigit() for char in value):
                continue
            entities.append(
                Entity(
                    start=match.start("value"),
                    end=match.end("value"),
                    label="CODE",
                    text=value,
                    source="rule",
                )
            )
        return entities

    def _find_long_codes(self, text: str) -> list[Entity]:
        entities = []
        for match in self.LONG_CODE_RE.finditer(text):
            value = match.group("value")
            compact = re.sub(r"[^A-Za-z0-9]", "", value)
            if len(compact) < 8:
                continue
            if not any(char.isalpha() for char in compact):
                continue
            if not any(char.isdigit() for char in compact):
                continue
            entities.append(
                Entity(
                    start=match.start("value"),
                    end=match.end("value"),
                    label="CODE",
                    text=value,
                    source="rule",
                )
            )
        return entities


def _is_valid_chinese_id_card(value: str) -> bool:
    if not re.fullmatch(r"\d{17}[\dX]", value):
        return False
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    checks = "10X98765432"
    total = sum(int(value[index]) * weights[index] for index in range(17))
    return checks[total % 11] == value[-1]


def _luhn_valid(value: str) -> bool:
    total = 0
    reverse_digits = value[::-1]
    for index, char in enumerate(reverse_digits):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0
