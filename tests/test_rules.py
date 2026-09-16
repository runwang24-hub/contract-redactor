from __future__ import annotations

from app.masker import mask_value
from app.rules import RuleDetector


def test_certificate_number_after_label_is_detected() -> None:
    text = "证件类型：【营业执照】\n证件号码：91110105078578697R"

    entities = RuleDetector().detect(text)

    certificate_entities = [
        entity for entity in entities if entity.label == "CERTIFICATE_NUMBER"
    ]
    assert [entity.text for entity in certificate_entities] == ["91110105078578697R"]
    assert [text[entity.start : entity.end] for entity in certificate_entities] == [
        "91110105078578697R"
    ]
    assert mask_value(
        certificate_entities[0].label, certificate_entities[0].text
    ) == "***"


def test_common_certificate_labels_are_supported() -> None:
    text = (
        "统一社会信用代码：91310000123456789X\n"
        "纳税人识别号: 1234567890ABCDEF\n"
        "组织机构代码 A123456789"
    )

    entities = RuleDetector().detect(text)

    assert [entity.text for entity in entities if entity.label == "CERTIFICATE_NUMBER"] == [
        "91310000123456789X",
        "1234567890ABCDEF",
        "A123456789",
    ]


def test_contract_number_is_treated_as_code() -> None:
    text = "合同编号：TGCF2511088695"

    entities = RuleDetector().detect(text)

    assert [(entity.label, entity.text) for entity in entities] == [
        ("CODE", "TGCF2511088695")
    ]


def test_short_numeric_values_after_code_labels_are_detected() -> None:
    text = "邮编：101500\n从业信息卡号：0457412"

    entities = RuleDetector().detect(text)

    assert [(entity.label, entity.text) for entity in entities] == [
        ("CODE", "101500"),
        ("CODE", "0457412"),
    ]


def test_property_certificate_number_with_chinese_characters_is_detected() -> None:
    text = "房屋权属证明/凭证：购房合同，编号：京（2018）朝不动产权第0069907号；"

    entities = RuleDetector().detect(text)

    assert [(entity.label, entity.text) for entity in entities] == [
        ("CODE", "京（2018）朝不动产权第0069907号")
    ]


def test_dates_and_amounts_are_not_treated_as_unlabelled_codes() -> None:
    text = "签约日期：2025年11月24日，合同金额：100000元。"

    entities = RuleDetector().detect(text)

    assert all(entity.label != "CODE" for entity in entities)
