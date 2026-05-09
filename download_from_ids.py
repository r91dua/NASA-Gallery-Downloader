#!/usr/bin/env python3
"""
Download NASA image IDs into a repo folder.

Default:
  - Reads nasa_ids.txt
  - Downloads high-res web JPGs like:
    https://images-assets.nasa.gov/image/art002e015231/art002e015231~large.jpg
  - Saves them into lunar_flyby_images/

Run locally:
  python download_from_ids.py

Run with custom folder:
  python download_from_ids.py --output images
"""

import argparse
import time
from pathlib import Path

import requests


def read_ids(path: Path) -> list[str]:
    ids = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ids.append(line)
    return ids


def download_file(url: str, output_path: Path) -> bool:
    if output_path.exists() and output_path.stat().st_size > 0:
        print(f"Skipping existing: {output_path}")
        return True

    print(f"Downloading: {url}")

    with requests.get(url, stream=True, timeout=120) as response:
        if response.status_code == 404:
            print(f"Not found: {url}")
            return False

        response.raise_for_status()

        temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        with temp_path.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)

        temp_path.replace(output_path)

    print(f"Saved: {output_path}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids-file", default="nasa_ids.txt")
    parser.add_argument("--output", default="lunar_flyby_images")
    parser.add_argument("--sleep", type=float, default=0.25)
    args = parser.parse_args()

    ids_file = Path(args.ids_file)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    nasa_ids = read_ids(ids_file)

    print(f"Found {len(nasa_ids)} NASA IDs in {ids_file}")
    print(f"Saving images to {output_dir}")

    success = 0
    failed = []

    for nasa_id in nasa_ids:
        image_url = f"https://images-assets.nasa.gov/image/{nasa_id}/{nasa_id}~large.jpg"
        output_path = output_dir / f"{nasa_id}~large.jpg"

        try:
            if download_file(image_url, output_path):
                success += 1
            else:
                failed.append(nasa_id)
        except Exception as exc:
            print(f"Failed {nasa_id}: {exc}")
            failed.append(nasa_id)

        time.sleep(args.sleep)

    print()
    print(f"Done. Downloaded/skipped successfully: {success}/{len(nasa_ids)}")

    if failed:
        print("Failed IDs:")
        for nasa_id in failed:
            print(nasa_id)

        # Non-zero exit makes GitHub Actions show the issue.
        raise SystemExit(1)


if __name__ == "__main__":
    main()
