from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_INPUTS = {".pdf", ".doc", ".docx"}


@dataclass(frozen=True, slots=True)
class RenderedPage:
    page_number: int
    path: Path
    width: int
    height: int


def prepare_pdf(input_path: str | Path, work_dir: str | Path) -> Path:
    """Return a PDF path, converting Word through LibreOffice when necessary."""
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.lower() not in SUPPORTED_INPUTS:
        raise ValueError(f"暂不支持的文件类型：{source.suffix or '<无扩展名>'}")
    if source.suffix.lower() == ".pdf":
        return source

    office = shutil.which("libreoffice") or shutil.which("soffice")
    if not office:
        raise RuntimeError("处理 Word 需要 LibreOffice，请先安装 LibreOffice")
    destination = Path(work_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [office, "--headless", "--convert-to", "pdf", "--outdir", str(destination), str(source)],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    pdf_path = destination / f"{source.stem}.pdf"
    if not pdf_path.is_file():
        raise RuntimeError("LibreOffice 未生成 PDF：" + pdf_path.name)
    return pdf_path


def render_pdf_pages(
    pdf_path: str | Path,
    output_dir: str | Path,
    dpi: int = 200,
) -> list[RenderedPage]:
    """Render every PDF page as a non-transparent PNG for OCR and masking."""
    if dpi <= 0:
        raise ValueError("dpi 必须大于 0")
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("请先安装 PyMuPDF 依赖") from exc

    source = Path(pdf_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    scale = dpi / 72.0
    pages: list[RenderedPage] = []
    with fitz.open(source) as document:
        for index, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            page_path = destination / f"page-{index:04d}.png"
            pixmap.save(page_path)
            pages.append(
                RenderedPage(
                    page_number=index,
                    path=page_path,
                    width=pixmap.width,
                    height=pixmap.height,
                )
            )
    return pages
