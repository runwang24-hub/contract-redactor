from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from app.document_loader import RenderedPage, prepare_pdf, render_pdf_pages
from app.entities import Entity
from app.llm_entities import DeepSeekEntityDetector
from app.span import merge_entities
from app.visual_regions import RedStampDetector, VisualRegion
from app.volc_ocr import OCRLine, MediaKitOCRClient


class EntityDetector(Protocol):
    def detect(self, text: str) -> list[Entity]:
        ...


@dataclass(frozen=True, slots=True)
class ProcessedPage:
    page_number: int
    image_path: Path
    entity_count: int
    ocr_line_count: int
    stamp_count: int = 0
    signature_field_count: int = 0


@dataclass(frozen=True, slots=True)
class DocumentRedactionResult:
    input_path: Path
    prepared_pdf: Path
    output_pdf: Path
    pages: list[ProcessedPage]


class DocumentRedactor:
    """MVP document flow: render every page, OCR, classify, and black-box."""

    def __init__(
        self,
        ocr_client: MediaKitOCRClient | None = None,
        entity_detector: EntityDetector | None = None,
        stamp_detector: RedStampDetector | None = None,
    ) -> None:
        self.ocr_client = ocr_client or MediaKitOCRClient()
        self.entity_detector = entity_detector or DeepSeekEntityDetector()
        self.stamp_detector = stamp_detector or RedStampDetector()

    def process(
        self,
        input_path: str | Path,
        output_pdf: str | Path,
        *,
        work_dir: str | Path,
        dpi: int = 200,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> DocumentRedactionResult:
        input_file = Path(input_path).expanduser().resolve()
        output_file = Path(output_pdf).expanduser().resolve()
        work = Path(work_dir).expanduser().resolve()
        work.mkdir(parents=True, exist_ok=True)
        if progress_callback:
            progress_callback("prepare", 0, 0)
        prepared_pdf = prepare_pdf(input_file, work / "converted")
        if progress_callback:
            progress_callback("render", 0, 0)
        rendered_pages = render_pdf_pages(prepared_pdf, work / "pages", dpi=dpi)
        if progress_callback:
            progress_callback("ocr", 0, len(rendered_pages))
        masked_dir = work / "masked"
        masked_dir.mkdir(parents=True, exist_ok=True)

        processed: list[ProcessedPage] = []
        for page in rendered_pages:
            ocr_result = self.ocr_client.recognize_file(page.path)
            rule_entities = _detect_rule_entities(ocr_result.text)
            try:
                semantic_entities = self.entity_detector.detect(ocr_result.text)
            except Exception as exc:  # Keep one slow LLM page from losing the PDF.
                print(
                    f"警告：第 {page.page_number} 页语义识别失败（{type(exc).__name__}），"
                    "继续使用规则识别和视觉区域脱敏。",
                    flush=True,
                )
                semantic_entities = []
            entities = merge_entities(rule_entities + semantic_entities)
            stamp_regions = self.stamp_detector.detect(page.path)
            signature_regions = signature_field_regions(
                ocr_result.lines,
                image_width=page.width,
                image_height=page.height,
            )
            masked_path = masked_dir / page.path.name
            mask_page(
                page.path,
                masked_path,
                ocr_result.lines,
                entities,
                visual_regions=stamp_regions + signature_regions,
            )
            processed.append(
                ProcessedPage(
                    page_number=page.page_number,
                    image_path=masked_path,
                    entity_count=len(entities),
                    ocr_line_count=len(ocr_result.lines),
                    stamp_count=len(stamp_regions),
                    signature_field_count=len(signature_regions),
                )
            )
            if progress_callback:
                progress_callback("ocr", len(processed), len(rendered_pages))

        output_file.parent.mkdir(parents=True, exist_ok=True)
        if progress_callback:
            progress_callback("export", len(processed), len(rendered_pages))
        create_image_pdf(processed, output_file, dpi=dpi)
        if progress_callback:
            progress_callback("complete", len(processed), len(rendered_pages))
        return DocumentRedactionResult(
            input_path=input_file,
            prepared_pdf=prepared_pdf,
            output_pdf=output_file,
            pages=processed,
        )


def _detect_rule_entities(text: str) -> list[Entity]:
    from app.rules import RuleDetector

    return RuleDetector().detect(text)


def mask_page(
    image_path: str | Path,
    output_path: str | Path,
    lines: list[OCRLine],
    entities: list[Entity],
    visual_regions: list[VisualRegion] | None = None,
) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("请先安装 Pillow 依赖") from exc

    source = Path(image_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        canvas = image.convert("RGB")
        draw = ImageDraw.Draw(canvas)
        for entity in entities:
            for box in _entity_boxes(entity, lines):
                draw.rectangle(box, fill="black")
        for region in visual_regions or []:
            draw.rectangle(region.bbox, fill="black")
        canvas.save(destination, format="PNG")


def signature_field_regions(
    lines: list[OCRLine],
    *,
    image_width: int,
    image_height: int,
) -> list[VisualRegion]:
    """Mask signature/stamp areas after signatory-style labels.

    This is deliberately structural rather than a general handwriting detector.
    It covers role labels such as ``授权代表：`` as well as the common
    ``出租人（签字或签章）：`` form. OCR often recognizes handwriting as text,
    so the region is masked even when the tail after the colon is non-empty.
    """
    import re

    labels = (
        "授权代表",
        "授权方",
        "授权人",
        "授权签字人",
        "法定代表人",
        "负责人",
        "签字代表",
        "签署人",
        "签名",
        "签字",
        "委托人",
        "受托人",
    )
    label_pattern = re.compile("|".join(re.escape(label) for label in labels))
    signature_marker_pattern = re.compile(r"签字(?:或(?:签章|盖章))?|签章|盖章")
    signatory_context_pattern = re.compile(
        r"出租人|承租人|房屋所有权人|委托代理人|代理人|授权|法人|负责人|从业人员"
    )
    regions: list[VisualRegion] = []
    for line in lines:
        if not line.bbox:
            continue
        text = line.text
        role_match = label_pattern.search(text)
        marker_match = signature_marker_pattern.search(text)
        if not role_match and not marker_match:
            continue

        # Prefer the colon following the role/marker. This catches both blank
        # fields and handwritten signatures that OCR turns into ordinary text.
        anchor = marker_match or role_match
        colon_match = re.search(r"[:：]", text[anchor.end() :]) if anchor else None
        colon_is_nearby = colon_match and colon_match.start() <= 24
        if colon_is_nearby:
            label_end = anchor.end() + colon_match.end()
        elif (
            marker_match
            and len(text) <= 80
            and signatory_context_pattern.search(text)
            and re.fullmatch(r"[）)】\]、，,。\s]*", text[marker_match.end() :].strip())
        ):
            # Some OCR results omit the colon on short signature rows. The
            # whole OCR line is still a strong enough structural signal.
            label_end = len(text)
        else:
            continue
        x0, y0, x1, y1 = _line_bbox(line)
        line_width = max(1, x1 - x0)
        text_length = max(1, len(text))
        start_x = x0 + round(line_width * label_end / text_length)
        if label_end >= len(line.text):
            start_x = x1
        line_height = max(1, y1 - y0)
        # Handwritten strokes can extend left of the OCR-estimated character
        # span. Keep the label visible, but overlap the area immediately after
        # the colon so the signature cannot peek out at the edge.
        start_x = max(0, start_x - line_height * 2)
        width = max(round(image_width * 0.28), line_height * 12)
        top = max(0, y0 - line_height * 6)
        bottom = min(image_height, y1 + line_height * 2)
        right = min(image_width, start_x + width)
        if right > start_x and bottom > top:
            regions.append(VisualRegion("signature_field", (start_x, top, right, bottom)))
    return regions


def _line_bbox(line: OCRLine) -> tuple[int, int, int, int]:
    bbox = line.bbox or {}
    raw_x0 = int(float(bbox.get("top_left_x", 0)))
    raw_y0 = int(float(bbox.get("top_left_y", 0)))
    raw_x1 = int(float(bbox.get("bottom_right_x", raw_x0)))
    raw_y1 = int(float(bbox.get("bottom_right_y", raw_y0)))
    x0, x1 = sorted((raw_x0, raw_x1))
    y0, y1 = sorted((raw_y0, raw_y1))
    return x0, y0, x1, y1


def _entity_boxes(entity: Entity, lines: list[OCRLine]) -> list[tuple[int, int, int, int]]:
    boxes: list[tuple[int, int, int, int]] = []
    cursor = 0
    for line in lines:
        line_start = cursor
        line_end = line_start + len(line.text)
        overlap_start = max(entity.start, line_start)
        overlap_end = min(entity.end, line_end)
        if overlap_start < overlap_end and line.bbox:
            local_start = overlap_start - line_start
            local_end = overlap_end - line_start
            boxes.append(_proportional_box(line, local_start, local_end))
        cursor = line_end + 1
    return boxes


def _proportional_box(line: OCRLine, start: int, end: int) -> tuple[int, int, int, int]:
    bbox = line.bbox or {}
    raw_x0 = int(float(bbox.get("top_left_x", 0)))
    raw_y0 = int(float(bbox.get("top_left_y", 0)))
    raw_x1 = int(float(bbox.get("bottom_right_x", raw_x0)))
    raw_y1 = int(float(bbox.get("bottom_right_y", raw_y0)))
    # OCR providers can occasionally return corners in reverse order. Normalize
    # them before calculating a partial-line rectangle.
    x0, x1 = sorted((raw_x0, raw_x1))
    y0, y1 = sorted((raw_y0, raw_y1))
    length = max(len(line.text), 1)
    left = x0 + round((x1 - x0) * max(0, min(start, length)) / length)
    right = x0 + round((x1 - x0) * max(0, min(end, length)) / length)
    padding = max(1, round((y1 - y0) * 0.08))
    right = max(right, left + 1)
    return (
        max(0, x0, left - padding),
        max(0, y0 - padding),
        max(left + 1, min(x1, right + padding)),
        max(y0 + 1, y1 + padding),
    )


def create_image_pdf(pages: list[ProcessedPage], output_path: Path, *, dpi: int) -> None:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("请先安装 PyMuPDF 依赖") from exc
    if not pages:
        raise ValueError("没有可输出的页面")
    if dpi <= 0:
        raise ValueError("dpi 必须大于 0")

    document = fitz.open()
    try:
        for page in pages:
            pixmap = fitz.Pixmap(str(page.image_path))
            width = pixmap.width * 72 / dpi
            height = pixmap.height * 72 / dpi
            pixmap = None
            pdf_page = document.new_page(width=width, height=height)
            pdf_page.insert_image(pdf_page.rect, filename=str(page.image_path))
        document.save(str(output_path), garbage=4, deflate=True)
    finally:
        document.close()
