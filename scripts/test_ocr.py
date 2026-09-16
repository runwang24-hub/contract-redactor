from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.volc_ocr import VolcengineOCRClient


def main() -> None:
    parser = argparse.ArgumentParser(description="测试火山引擎 AI MediaKit OCR API")
    parser.add_argument("image", type=Path, help="本地图片路径；程序会先上传到 MediaKit")
    parser.add_argument("--save-json", type=Path, help="保存完整 OCR JSON")
    args = parser.parse_args()

    result = VolcengineOCRClient().recognize_file(args.image)
    print("识别文字：")
    print(result.text)
    print(f"识别行数：{len(result.lines)}")
    for index, line in enumerate(result.lines, start=1):
        print(f"[{index}] {line.text} | bbox={line.bbox} | confidence={line.confidence}")
    if args.save_json:
        args.save_json.parent.mkdir(parents=True, exist_ok=True)
        args.save_json.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"完整结果已保存：{args.save_json}")


if __name__ == "__main__":
    main()
