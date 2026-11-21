#!/usr/bin/env python3
"""Resize an image to a 4:1 aspect ratio."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageOps


ASPECT_RATIO = 4 / 1


def output_size(width: int, height: int, target_width: int | None) -> tuple[int, int]:
    if target_width is None:
        if width / height >= ASPECT_RATIO:
            return width, round(width / ASPECT_RATIO)
        return round(height * ASPECT_RATIO), height

    return target_width, round(target_width / ASPECT_RATIO)


def rescale_4x1(
    input_path: Path,
    output_path: Path,
    *,
    mode: str,
    target_width: int | None,
    background: str,
) -> None:
    with Image.open(input_path) as image:
        image = ImageOps.exif_transpose(image)
        size = output_size(image.width, image.height, target_width)

        if mode == "crop":
            resized = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
        else:
            resized = ImageOps.pad(
                image,
                size,
                method=Image.Resampling.LANCZOS,
                color=background,
            )

        if output_path.suffix.lower() in {".jpg", ".jpeg"}:
            resized = resized.convert("RGB")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        resized.save(output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resize an image to a 4:1 aspect ratio.",
    )
    parser.add_argument("input", type=Path, help="Image to resize")
    parser.add_argument("output", type=Path, help="Where to write the resized image")
    parser.add_argument(
        "--mode",
        choices=("crop", "pad"),
        default="crop",
        help="crop fills 4:1 by trimming edges; pad keeps the full image with borders",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        help="Optional output width in pixels; height is width / 4",
    )
    parser.add_argument(
        "--background",
        default="white",
        help="Padding color for --mode pad, such as white, black, or #f5f5f5",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rescale_4x1(
        args.input,
        args.output,
        mode=args.mode,
        target_width=args.width,
        background=args.background,
    )


if __name__ == "__main__":
    main()
