from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.document_redactor import signature_field_regions
from app.volc_ocr import OCRLine
from app.visual_regions import RedStampDetector


def test_red_stamp_detector_finds_large_red_region(tmp_path: Path) -> None:
    image_path = tmp_path / "stamp.png"
    image = Image.new("RGB", (240, 240), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((50, 50, 190, 190), outline=(220, 60, 60), width=6)
    image.save(image_path)

    regions = RedStampDetector().detect(image_path)

    assert len(regions) == 1
    left, top, right, bottom = regions[0].bbox
    assert left <= 50 and top <= 50
    assert right >= 190 and bottom >= 190


def test_signature_structure_matches_signatory_fields_with_handwriting() -> None:
    lines = [
        OCRLine("授权代表：李四", {"top_left_x": 100, "top_left_y": 200, "bottom_right_x": 250, "bottom_right_y": 220}),
        OCRLine("承租人（签字或签章）：张三", {"top_left_x": 100, "top_left_y": 300, "bottom_right_x": 320, "bottom_right_y": 320}),
        OCRLine("地址：", {"top_left_x": 100, "top_left_y": 400, "bottom_right_x": 220, "bottom_right_y": 420}),
    ]
    regions = signature_field_regions(lines, image_width=1000, image_height=1000)
    assert len(regions) == 2
    assert all(region.kind == "signature_field" for region in regions)
    assert regions[0].bbox[0] > 100


def test_ordinary_text_is_not_a_signature_field() -> None:
    lines = [
        OCRLine("本合同签字后生效，双方应按约履行。", {"top_left_x": 100, "top_left_y": 200, "bottom_right_x": 350, "bottom_right_y": 220}),
        OCRLine("签字盖章", {"top_left_x": 100, "top_left_y": 300, "bottom_right_x": 220, "bottom_right_y": 320}),
    ]
    assert signature_field_regions(lines, image_width=1000, image_height=1000) == []
