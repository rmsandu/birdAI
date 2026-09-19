"""Download and extract the CUB-200-2011 dataset.

CUB-200-2011 ("Caltech-UCSD Birds-200-2011") is a fine-grained bird species
classification dataset: 11,788 images across 200 species. The canonical
download link lives on the Caltech Vision group's data page and has moved
in the past; if the URL below stops working, download the archive manually
from https://www.vision.caltech.edu/datasets/cub_200_2011/ and place
CUB_200_2011.tgz in the target data directory before re-running this script
with --skip-if-exists.
"""

import argparse
import sys
import tarfile
from pathlib import Path

import httpx

CUB200_URL = (
    "https://data.caltech.edu/records/65de6-vp158/files/CUB_200_2011.tgz"
)
ARCHIVE_NAME = "CUB_200_2011.tgz"
EXPECTED_TOP_LEVEL_ENTRIES = {
    "images",
    "images.txt",
    "classes.txt",
    "image_class_labels.txt",
    "train_test_split.txt",
    "bounding_boxes.txt",
}


def download_archive(archive_path: Path) -> None:
    print(f"Downloading CUB-200-2011 from {CUB200_URL} ...")
    try:
        with httpx.stream("GET", CUB200_URL, follow_redirects=True, timeout=60) as response:
            response.raise_for_status()
            with archive_path.open("wb") as out_file:
                for chunk in response.iter_bytes():
                    out_file.write(chunk)
    except httpx.HTTPError as exc:
        raise RuntimeError(
            "Failed to download CUB-200-2011 automatically "
            f"({exc}). Download it manually from "
            "https://www.vision.caltech.edu/datasets/cub_200_2011/ and place "
            f"'{ARCHIVE_NAME}' at {archive_path}, then re-run with --skip-if-exists."
        ) from exc


def extract_archive(archive_path: Path, data_dir: Path) -> Path:
    print(f"Extracting {archive_path} ...")
    with tarfile.open(archive_path) as tar:
        tar.extractall(path=data_dir, filter="data")

    extracted_dir = data_dir / "CUB_200_2011"
    if not extracted_dir.exists():
        raise RuntimeError(
            f"Extraction finished but {extracted_dir} was not found. "
            "The archive layout may have changed."
        )
    return extracted_dir


def verify_extraction(extracted_dir: Path) -> None:
    missing = [
        entry
        for entry in EXPECTED_TOP_LEVEL_ENTRIES
        if not (extracted_dir / entry).exists()
    ]
    if missing:
        raise RuntimeError(
            f"CUB-200-2011 extraction at {extracted_dir} looks incomplete; "
            f"missing: {', '.join(sorted(missing))}. Delete the directory and re-run."
        )
    image_count = sum(1 for _ in (extracted_dir / "images").rglob("*.jpg"))
    if image_count < 11000:
        raise RuntimeError(
            f"Expected ~11,788 images in {extracted_dir / 'images'}, found "
            f"{image_count}. The download may be truncated or corrupted."
        )
    print(f"Verified {image_count} images in {extracted_dir / 'images'}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        default=Path(__file__).resolve().parent.parent / "data",
        type=Path,
    )
    parser.add_argument(
        "--skip-if-exists",
        action="store_true",
        help="Skip downloading/extracting if CUB_200_2011/ already looks complete.",
    )
    args = parser.parse_args()

    data_dir: Path = args.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    extracted_dir = data_dir / "CUB_200_2011"
    archive_path = data_dir / ARCHIVE_NAME

    if args.skip_if_exists and extracted_dir.exists():
        try:
            verify_extraction(extracted_dir)
            print("CUB-200-2011 already present and verified; skipping.")
            return
        except RuntimeError as exc:
            print(f"Existing extraction failed verification ({exc}); re-downloading.")

    if not archive_path.exists():
        download_archive(archive_path)
    else:
        print(f"Found existing archive at {archive_path}; skipping download.")

    extract_archive(archive_path, data_dir)
    verify_extraction(extracted_dir)
    print(f"CUB-200-2011 ready at {extracted_dir}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
