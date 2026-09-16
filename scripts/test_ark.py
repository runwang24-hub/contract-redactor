from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ark_client import ArkModelClient


VISION_PROMPT = "请读取这张合同页面，只输出你看到的文字内容，不要解释。"
TEXT_PROMPT = "请从文本中找出人名、公司名称和详细地址，只返回原文中出现的内容。"


def main() -> None:
    parser = argparse.ArgumentParser(description="测试豆包 Vision 或 DeepSeek API")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--image", type=Path, help="调用豆包 Vision 的本地图片")
    group.add_argument("--text", help="调用 DeepSeek 的文本")
    args = parser.parse_args()

    client = ArkModelClient()
    if args.image:
        print(client.analyze_image(args.image, VISION_PROMPT))
    else:
        print(client.analyze_text(args.text, TEXT_PROMPT))


if __name__ == "__main__":
    main()
