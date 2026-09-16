from __future__ import annotations

from app.llm_entities import DeepSeekEntityDetector


class FakeClient:
    def analyze_text(self, text: str, prompt: str) -> str:
        return '[{"text":"刘凤良","label":"PERSON"}]'


def test_repeated_entity_is_detected_at_every_occurrence() -> None:
    text = "授权代表：刘凤良。合伙人刘凤良等律师。"
    entities = DeepSeekEntityDetector(FakeClient()).detect(text)
    assert [entity.text for entity in entities] == ["刘凤良", "刘凤良"]
    assert [text[entity.start : entity.end] for entity in entities] == ["刘凤良", "刘凤良"]
