#!/usr/bin/env python3
"""
Download NASA gallery images/videos into folders in this GitHub repo.

Default behavior:
  - Reads gallery URLs from galleries.txt
  - Scans paginated NASA gallery pages automatically
  - Opens each NASA image/video detail page
  - Uses the official "Download" link when available
  - Falls back to NASA Images API and direct CDN patterns when needed
  - Saves files into nasa_downloads/<gallery-slug>/
  - Does NOT fail the whole workflow for one bad/403 item

Run locally:
  pip install requests
  python download_nasa_galleries.py

Run custom:
  python download_nasa_galleries.py --galleries-file galleries.txt --output nasa_downloads
"""

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse, unquote

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 NASA Gallery Downloader for personal archive"
}

ASSET_API = "https://images-api.nasa.gov/asset/{nasa_id}"

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v", ".avi")
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS


def slugify(value: str) -> str:
    parsed = urlparse(value)
    path = parsed.path.strip("/")
    slug = path.split("/")[-1] if path else parsed.netloc
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", slug).strip("_")
    return slug or "nasa_gallery"


def read_gallery_urls(path: Path) -> list[str]:
    urls = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line.rstrip("/") + "/")
    return urls


def get(url: str, *, stream: bool = False) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=180, stream=stream)
    return response


def get_text(url: str) -> str:
    response = get(url)
    response.raise_for_status()
    return response.text


def unique_keep_order(items: Iterable[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if not item:
            continue
        key = item.strip()
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def gallery_page_url(base_url: str, page: int) -> str:
    if page == 1:
        return base_url
    return urljoin(base_url, f"page/{page}/")


def extract_detail_links(html: str, base_url: str) -> list[str]:
    # NASA galleries link detail pages as /image-detail/... or /video-detail/...
    links = re.findall(r'href=["\']([^"\']+/(?:image-detail|video-detail)/[^"\']+)["\']', html, flags=re.I)
    absolute = [urljoin(base_url, link).split("#")[0] for link in links]
    return unique_keep_order(absolute)


def discover_detail_pages(gallery_url: str, max_pages: int) -> list[str]:
    detail_pages = []

    for page in range(1, max_pages + 1):
        url = gallery_page_url(gallery_url, page)
        print(f"Scanning gallery page {page}: {url}")

        response = get(url)
        if response.status_code == 404:
            print(f"Page {page} returned 404. Stopping pagination.")
            break

        response.raise_for_status()
        links = extract_detail_links(response.text, url)

        if not links:
            print(f"No detail links found on page {page}. Stopping pagination.")
            break

        print(f"Found {len(links)} detail page link(s).")
        detail_pages.extend(links)

    return unique_keep_order(detail_pages)


def extract_download_links(detail_html: str, detail_url: str) -> list[str]:
    # Prefer direct NASA asset links from href attributes.
    links = re.findall(r'href=["\']([^"\']*images-assets\.nasa\.gov[^"\']+)["\']', detail_html, flags=re.I)
    links += re.findall(r'(https://images-assets\.nasa\.gov/[^\s"\'<>]+)', detail_html, flags=re.I)

    # Clean common HTML escaping.
    cleaned = []
    for link in links:
        link = link.replace("&amp;", "&")
        link = unquote(link)
        cleaned.append(link)

    return unique_keep_order(cleaned)


def extract_nasa_ids(text: str) -> list[str]:
    # Covers IDs like art002e009280, jsc2026e020490, cmasaw1_20260402015754_3,
    # and Orion video/media IDs like art002m1200912239A.
    patterns = [
        r"\bart\d{3}e\d{6}\b",
        r"\bart\d{3}m[0-9A-Za-z_-]{6,}\b",
        r"\bjsc\d{4}e\d{6}\b",
        r"\bcmasaw1_[0-9A-Za-z_-]+\b",
        r"\biss\d{3}e\d{6}\b",
    ]

    ids = []
    for pattern in patterns:
        ids.extend(re.findall(pattern, text, flags=re.I))
    return unique_keep_order(ids)


def media_url_score(url: str, prefer_large: bool) -> int:
    lower = url.lower()
    score = 0

    if any(lower.endswith(ext) for ext in MEDIA_EXTENSIONS):
        score += 100

    if prefer_large:
        # Web-friendly high-res JPG/MP4 preferred.
        if "~large" in lower:
            score += 80
        if lower.endswith((".jpg", ".jpeg")):
            score += 40
        if "~orig" in lower or "~original" in lower:
            score += 20
        if lower.endswith((".tif", ".tiff")):
            score -= 30
    else:
        # Original/largest preferred.
        if "~orig" in lower or "~original" in lower:
            score += 80
        if lower.endswith((".tif", ".tiff")):
            score += 60
        if "~large" in lower:
            score += 40

    if lower.endswith((".mp4", ".mov", ".m4v")):
        score += 50

    # Avoid thumbnails when possible.
    if "thumb" in lower or "~small" in lower:
        score -= 50

    return score


def choose_best_url(urls: list[str], prefer_large: bool) -> str | None:
    media_urls = [u for u in urls if any(urlparse(u).path.lower().endswith(ext) for ext in MEDIA_EXTENSIONS)]
    if not media_urls:
        return None

    media_urls.sort(key=lambda u: media_url_score(u, prefer_large), reverse=True)
    return media_urls[0]


def asset_api_urls(nasa_id: str) -> list[str]:
    url = ASSET_API.format(nasa_id=nasa_id)
    response = get(url)
    if response.status_code >= 400:
        return []

    try:
        data = response.json()
    except json.JSONDecodeError:
        return []

    items = data.get("collection", {}).get("items", [])
    urls = [item.get("href", "") for item in items if item.get("href")]
    return unique_keep_order(urls)


def guess_direct_large_url(nasa_id: str) -> str:
    return f"https://images-assets.nasa.gov/image/{nasa_id}/{nasa_id}~large.jpg"


def filename_from_url(url: str, fallback_name: str) -> str:
    path = urlparse(url).path
    name = Path(path).name
    name = unquote(name)
    name = re.sub(r"[^a-zA-Z0-9._~+-]+", "_", name).strip("_")
    if not name or "." not in name:
        name = fallback_name
    return name[:180]


def download_file(url: str, output_path: Path) -> bool:
    if output_path.exists() and output_path.stat().st_size > 0:
        print(f"Skipping existing: {output_path}")
        return True

    print(f"Downloading: {url}")
    response = get(url, stream=True)

    if response.status_code in (403, 404):
        print(f"Not available ({response.status_code}): {url}")
        return False

    response.raise_for_status()

    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with tmp_path.open("wb") as file:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                file.write(chunk)

    tmp_path.replace(output_path)
    print(f"Saved: {output_path}")
    return True


def process_detail_page(detail_url: str, gallery_output_dir: Path, prefer_large: bool, sleep: float) -> tuple[bool, str]:
    print(f"Reading detail page: {detail_url}")

    try:
        html = get_text(detail_url)
    except Exception as exc:
        return False, f"Could not read detail page {detail_url}: {exc}"

    nasa_ids = extract_nasa_ids(detail_url + "\n" + html)
    download_links = extract_download_links(html, detail_url)

    candidate_urls = []

    # Official page Download href usually comes first and is best.
    candidate_urls.extend(download_links)

    # NASA asset API fallback.
    for nasa_id in nasa_ids:
        candidate_urls.extend(asset_api_urls(nasa_id))

    # Direct CDN large fallback.
    for nasa_id in nasa_ids:
        candidate_urls.append(guess_direct_large_url(nasa_id))

    candidate_urls = unique_keep_order(candidate_urls)
    best_url = choose_best_url(candidate_urls, prefer_large=prefer_large)

    if not best_url:
        short_hash = hashlib.sha1(detail_url.encode()).hexdigest()[:8]
        return False, f"No downloadable media URL found for {detail_url} ({short_hash})"

    fallback_id = nasa_ids[0] if nasa_ids else hashlib.sha1(detail_url.encode()).hexdigest()[:12]
    filename = filename_from_url(best_url, f"{fallback_id}.jpg")

    # Prefix filename with ID when the URL filename is too generic.
    if nasa_ids and not filename.lower().startswith(nasa_ids[0].lower()):
        filename = f"{nasa_ids[0]}_{filename}"

    output_path = gallery_output_dir / filename

    ok = download_file(best_url, output_path)
    time.sleep(sleep)

    if ok:
        return True, str(output_path)

    # Try remaining candidates if the first was forbidden.
    for alt_url in candidate_urls:
        if alt_url == best_url:
            continue
        if not any(urlparse(alt_url).path.lower().endswith(ext) for ext in MEDIA_EXTENSIONS):
            continue

        alt_filename = filename_from_url(alt_url, f"{fallback_id}.jpg")
        if nasa_ids and not alt_filename.lower().startswith(nasa_ids[0].lower()):
            alt_filename = f"{nasa_ids[0]}_{alt_filename}"

        alt_output_path = gallery_output_dir / alt_filename

        try:
            if download_file(alt_url, alt_output_path):
                time.sleep(sleep)
                return True, str(alt_output_path)
        except Exception as exc:
            print(f"Alternative failed: {alt_url} -> {exc}")

    return False, f"All candidate downloads failed for {detail_url}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--galleries-file", default="galleries.txt")
    parser.add_argument("--output", default="nasa_downloads")
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument("--prefer-large", action="store_true", default=True)
    parser.add_argument("--fail-on-errors", action="store_true", help="Fail workflow if any item fails")
    args = parser.parse_args()

    galleries_file = Path(args.galleries_file)
    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)

    gallery_urls = read_gallery_urls(galleries_file)

    total_ok = 0
    total_failed = 0
    failures: list[str] = []

    for gallery_url in gallery_urls:
        gallery_slug = slugify(gallery_url)
        gallery_output_dir = output_root / gallery_slug
        gallery_output_dir.mkdir(parents=True, exist_ok=True)

        print()
        print("=" * 80)
        print(f"Gallery: {gallery_url}")
        print(f"Output:  {gallery_output_dir}")
        print("=" * 80)

        detail_pages = discover_detail_pages(gallery_url, args.max_pages)
        print(f"Total unique detail pages: {len(detail_pages)}")

        for detail_url in detail_pages:
            try:
                ok, message = process_detail_page(
                    detail_url=detail_url,
                    gallery_output_dir=gallery_output_dir,
                    prefer_large=args.prefer_large,
                    sleep=args.sleep,
                )
                if ok:
                    total_ok += 1
                else:
                    total_failed += 1
                    failures.append(message)
                    print(f"FAILED: {message}")
            except Exception as exc:
                total_failed += 1
                msg = f"Unexpected failure for {detail_url}: {exc}"
                failures.append(msg)
                print(f"FAILED: {msg}")

    manifest = {
        "successful_downloads_or_existing_files": total_ok,
        "failed_items": total_failed,
        "failures": failures,
    }

    manifest_path = output_root / "_download_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print()
    print(json.dumps(manifest, indent=2))

    if failures:
        print()
        print("Some files failed, but successful files were preserved.")
        print(f"See {manifest_path}")

    if failures and args.fail_on_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
