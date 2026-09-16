from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class VisualRegion:
    kind: str
    bbox: tuple[int, int, int, int]
    score: float = 0.9


class RedStampDetector:
    """Find red stamp-like regions without asking a model to guess.

    This is intentionally conservative: it targets sufficiently large red
    connected regions and ignores small red scan marks and edge noise.
    """

    def detect(self, image_path: str | Path) -> list[VisualRegion]:
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("请先安装 Pillow 依赖") from exc

        path = Path(image_path)
        with Image.open(path).convert("RGB") as image:
            width, height = image.size
            factor = 4 if min(width, height) >= 800 else 2
            small = image.resize(
                (max(1, width // factor), max(1, height // factor)),
                Image.Resampling.BILINEAR,
            )
            mask = _red_mask(small)
            mask = _dilate(mask, small.width, small.height, radius=2)
            components = _components(mask, small.width, small.height)

        regions: list[VisualRegion] = []
        for count, min_x, min_y, max_x, max_y in components:
            box_width = (max_x - min_x + 1) * factor
            box_height = (max_y - min_y + 1) * factor
            if count < 80 or box_width < 80 or box_height < 40:
                continue
            if max(box_width, box_height) / max(1, min(box_width, box_height)) > 4.5:
                continue
            padding = max(8, factor * 3)
            left = max(0, min_x * factor - padding)
            top = max(0, min_y * factor - padding)
            right = min(width, (max_x + 1) * factor + padding)
            bottom = min(height, (max_y + 1) * factor + padding)
            regions.append(VisualRegion("stamp", (left, top, right, bottom)))
        return regions


def _red_mask(image) -> bytearray:
    width, height = image.size
    pixels = image.load()
    mask = bytearray(width * height)
    for y in range(height):
        for x in range(width):
            red, green, blue = pixels[x, y]
            if (
                red >= 110
                and red - green >= 28
                and red - blue >= 28
                and red >= green * 1.18
                and red >= blue * 1.18
            ):
                mask[y * width + x] = 1
    return mask


def _dilate(mask: bytearray, width: int, height: int, radius: int) -> bytearray:
    output = bytearray(mask)
    for y in range(height):
        for x in range(width):
            if not mask[y * width + x]:
                continue
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < width and 0 <= yy < height:
                        output[yy * width + xx] = 1
    return output


def _components(mask: bytearray, width: int, height: int) -> list[tuple[int, int, int, int, int]]:
    seen = bytearray(width * height)
    output: list[tuple[int, int, int, int, int]] = []
    for y in range(height):
        for x in range(width):
            index = y * width + x
            if not mask[index] or seen[index]:
                continue
            queue = [(x, y)]
            seen[index] = 1
            count = 0
            min_x = min_y = width + height
            max_x = max_y = -1
            cursor = 0
            while cursor < len(queue):
                current_x, current_y = queue[cursor]
                cursor += 1
                count += 1
                min_x = min(min_x, current_x)
                min_y = min(min_y, current_y)
                max_x = max(max_x, current_x)
                max_y = max(max_y, current_y)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    next_x, next_y = current_x + dx, current_y + dy
                    if not (0 <= next_x < width and 0 <= next_y < height):
                        continue
                    next_index = next_y * width + next_x
                    if mask[next_index] and not seen[next_index]:
                        seen[next_index] = 1
                        queue.append((next_x, next_y))
            output.append((count, min_x, min_y, max_x, max_y))
    return output
