from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.document_redactor import DocumentRedactor


def main() -> None:
    parser = argparse.ArgumentParser(description="合同文档 OCR 脱敏 MVP")
    parser.add_argument("input", type=Path, help="PDF、DOC 或 DOCX 文件")
    parser.add_argument("output", type=Path, help="输出图片型 PDF 路径")
    parser.add_argument("--work-dir", type=Path, default=Path("output/document-work"))
    parser.add_argument("--dpi", type=int, default=200)
    args = parser.parse_args()

    result = DocumentRedactor().process(
        args.input,
        args.output,
        work_dir=args.work_dir,
        dpi=args.dpi,
    )
    print(f"输入：{result.input_path}")
    print(f"输出：{result.output_pdf}")
    print(f"页数：{len(result.pages)}")
    for page in result.pages:
        print(
            f"第 {page.page_number} 页：OCR {page.ocr_line_count} 行，"
            f"文字遮盖 {page.entity_count} 项，"
            f"印章 {page.stamp_count} 个，"
            f"签字字段 {page.signature_field_count} 个"
        )


if __name__ == "__main__":
    main()
