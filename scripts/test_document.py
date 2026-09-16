from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.document_loader import prepare_pdf, render_pdf_pages


def main() -> None:
    parser = argparse.ArgumentParser(description="测试 PDF/Word 文档转换和分页渲染")
    parser.add_argument("document", type=Path, help="PDF、DOC 或 DOCX 文件")
    parser.add_argument("--out-dir", type=Path, default=Path("output/pages"))
    parser.add_argument("--dpi", type=int, default=200)
    args = parser.parse_args()

    pdf_path = prepare_pdf(args.document, args.out_dir / "converted")
    pages = render_pdf_pages(pdf_path, args.out_dir / "rendered", dpi=args.dpi)
    print(f"PDF：{pdf_path}")
    print(f"页数：{len(pages)}")
    for page in pages:
        print(f"第 {page.page_number} 页：{page.path} ({page.width}x{page.height})")


if __name__ == "__main__":
    main()
