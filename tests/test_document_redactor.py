from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.document_redactor import _entity_boxes, create_image_pdf, mask_page
from app.entities import Entity
from app.volc_ocr import OCRLine


def test_entity_box_uses_part_of_ocr_line() -> None:
    line = OCRLine(
        text="电话：13800138000",
        bbox={
            "top_left_x": 100,
            "top_left_y": 50,
            "bottom_right_x": 300,
            "bottom_right_y": 70,
        },
    )
    entity = Entity(3, 14, "PHONE", "13800138000", "rule")
    boxes = _entity_boxes(entity, [line])
    assert len(boxes) == 1
    assert boxes[0][0] > 100
    assert boxes[0][2] <= 300


def test_mask_page_and_create_image_pdf(tmp_path: Path) -> None:
    source = tmp_path / "page.png"
    masked = tmp_path / "masked.png"
    output = tmp_path / "result.pdf"
    Image.new("RGB", (400, 200), "white").save(source)
    line = OCRLine(
        text="张三",
        bbox={
            "top_left_x": 100,
            "top_left_y": 50,
            "bottom_right_x": 200,
            "bottom_right_y": 80,
        },
    )
    entity = Entity(0, 2, "PERSON", "张三", "deepseek")
    mask_page(source, masked, [line], [entity])
    with Image.open(masked) as image:
        assert image.getpixel((150, 65)) == (0, 0, 0)
    from app.document_redactor import ProcessedPage

    create_image_pdf([ProcessedPage(1, masked, 1, 1)], output, dpi=200)
    assert output.is_file()
    assert output.stat().st_size > 0
