#!/usr/bin/env python3
"""Import reviewed wger exercise thumbnails and attribution metadata."""

from __future__ import annotations

import argparse
import json
import re
import ssl
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "src/data/exercises.json"
DEFAULT_OVERRIDES = ROOT / "scripts/wger-overrides.json"
DEFAULT_MEDIA_DIR = ROOT / "copilot/assets/exercises/wger"
DEFAULT_JS = ROOT / "copilot/js/exercise-media.js"
DEFAULT_REPORT = ROOT / "scripts/wger-match-report.json"
API_URL = "https://wger.de/api/v2/exerciseinfo/"
LICENSE_API_URL = "https://wger.de/api/v2/license/?limit=100"
USER_AGENT = "DietTrackerExerciseMediaImporter/1.0"


def ssl_context() -> ssl.SSLContext:
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


SSL_CONTEXT = ssl_context()


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def request_json(url: str) -> dict:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=45, context=SSL_CONTEXT) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError) as error:
        raise RuntimeError(f"wger request failed: {url}: {error}") from error


def fetch_exercises() -> list[dict]:
    exercises: list[dict] = []
    url = f"{API_URL}?limit=100&offset=0"
    while url:
        payload = request_json(url)
        exercises.extend(payload.get("results", []))
        url = payload.get("next")
        if url:
            time.sleep(0.12)
    return exercises


def fetch_licenses() -> dict[int, dict]:
    payload = request_json(LICENSE_API_URL)
    return {int(item["id"]): item for item in payload.get("results", [])}


def candidate_names(exercise: dict) -> set[str]:
    names: set[str] = set()
    for translation in exercise.get("translations") or []:
        names.add(normalize(translation.get("name", "")))
        for alias in translation.get("aliases") or []:
            names.add(normalize(alias.get("alias", "")))
    return {name for name in names if name}


def local_names(exercise: dict) -> set[str]:
    values = [exercise.get("name", ""), *(exercise.get("aliases") or [])]
    return {normalize(value) for value in values if normalize(value)}


def name_score(left_names: set[str], right_names: set[str]) -> float:
    if left_names & right_names:
        return 100.0
    best = 0.0
    for left in left_names:
        left_tokens = set(left.split())
        for right in right_names:
            if min(len(left), len(right)) >= 6 and (left in right or right in left):
                best = max(best, 91.0)
            ratio = SequenceMatcher(None, left, right).ratio() * 100
            right_tokens = set(right.split())
            union = left_tokens | right_tokens
            token_score = (len(left_tokens & right_tokens) / len(union) * 92) if union else 0
            best = max(best, ratio, token_score)
    return round(best, 2)


def select_image(exercise: dict, exclude_ai: bool, image_id: Optional[int] = None) -> Optional[dict]:
    images = list(exercise.get("images") or [])
    if exclude_ai:
        images = [image for image in images if not image.get("is_ai_generated")]
    if image_id is not None:
        return next((image for image in images if int(image.get("id", 0)) == image_id), None)
    if not images:
        return None
    images.sort(key=lambda image: (bool(image.get("is_ai_generated")), not image.get("is_main")))
    return images[0]


def image_license(image: dict, licenses: dict[int, dict]) -> dict:
    license_value = image.get("license")
    if isinstance(license_value, dict):
        return license_value
    return licenses.get(int(license_value or 0), {})


def accepted_license(image: dict, licenses: dict[int, dict]) -> bool:
    short_name = str(image_license(image, licenses).get("short_name", "")).upper()
    return short_name.startswith("CC")


def rank_candidates(
    local: dict, remote: list[dict], licenses: dict[int, dict], exclude_ai: bool
) -> list[tuple[float, dict, dict]]:
    ranked: list[tuple[float, dict, dict]] = []
    wanted_names = local_names(local)
    for exercise in remote:
        image = select_image(exercise, exclude_ai)
        if not image or not accepted_license(image, licenses):
            continue
        score = name_score(wanted_names, candidate_names(exercise))
        if score:
            ranked.append((score, exercise, image))
    return sorted(ranked, key=lambda item: (-item[0], item[1].get("id", 0)))


def load_overrides(path: Path) -> dict[str, dict[str, int]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(key): {"exercise_id": int(value["exercise_id"]), "image_id": int(value["image_id"])}
        for key, value in payload.items()
    }


def choose_matches(
    catalog: list[dict],
    remote: list[dict],
    licenses: dict[int, dict],
    overrides: dict[str, dict[str, int]],
    threshold: float,
    exclude_ai: bool,
    allow_automatic: bool,
) -> tuple[list[dict], list[dict]]:
    by_id = {int(exercise["id"]): exercise for exercise in remote}
    selected: list[dict] = []
    report: list[dict] = []
    for local in catalog:
        ranked = rank_candidates(local, remote, licenses, exclude_ai)
        override = overrides.get(local["key"])
        if override is not None:
            exercise = by_id.get(override["exercise_id"])
            image = select_image(exercise or {}, False, override["image_id"])
            if not exercise or not image or not accepted_license(image, licenses):
                raise RuntimeError(f"Invalid wger override for {local['key']}: {override}")
            if exclude_ai and image.get("is_ai_generated"):
                choice = None
                reason = "unmatched"
            else:
                choice = (100.0, exercise, image)
                reason = "override"
        elif allow_automatic and ranked and ranked[0][0] >= threshold:
            choice = ranked[0]
            reason = "automatic"
        else:
            choice = None
            reason = "unmatched"

        alternatives = [
            {
                "score": score,
                "wger_id": exercise["id"],
                "names": sorted(candidate_names(exercise))[:8],
                "has_ai_image": bool(image.get("is_ai_generated")),
            }
            for score, exercise, image in ranked[:3]
        ]
        report_entry = {
            "key": local["key"],
            "name": local["name"],
            "status": reason,
            "alternatives": alternatives,
        }
        if choice:
            score, exercise, image = choice
            report_entry.update({"score": score, "wger_id": exercise["id"]})
            selected.append({"local": local, "remote": exercise, "image": image, "score": score})
        report.append(report_entry)
    return selected, report


def download_image(url: str, destination_base: Path) -> Path:
    if urlparse(url).hostname != "wger.de":
        raise RuntimeError(f"Unexpected image host: {url}")
    request = Request(url, headers={"Accept": "image/*", "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=45, context=SSL_CONTEXT) as response:
            content_type = response.headers.get_content_type()
            content = response.read(2_000_001)
    except (HTTPError, URLError, TimeoutError) as error:
        raise RuntimeError(f"Image download failed: {url}: {error}") from error
    signatures = {
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP",
    }
    if len(content) > 2_000_000 or not signatures.get(content_type, False):
        raise RuntimeError(f"Invalid image response: {url} ({content_type}, {len(content)} bytes)")
    extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[content_type]
    destination = destination_base.with_suffix(extension)
    destination.write_bytes(content)
    return destination


def attribution(match: dict, local_path: Path, licenses: dict[int, dict]) -> dict:
    exercise = match["remote"]
    image = match["image"]
    license_data = image_license(image, licenses)
    author = image.get("license_author") or "wger community"
    return {
        "key": match["local"]["key"],
        "name": match["local"]["name"],
        "image": local_path.relative_to(ROOT / "copilot").as_posix(),
        "image_id": image["id"],
        "wger_id": exercise["id"],
        "wger_uuid": exercise.get("uuid"),
        "source_url": f"https://wger.de/api/v2/exerciseinfo/{exercise['id']}/",
        "original_image_url": image.get("image"),
        "author": author,
        "author_url": image.get("license_author_url") or "",
        "license_title": image.get("license_title") or "",
        "object_url": image.get("license_object_url") or "",
        "derivative_source_url": image.get("license_derivative_source_url") or "",
        "license": license_data.get("short_name") or license_data.get("full_name") or "Creative Commons",
        "license_url": license_data.get("url") or "",
        "is_ai_generated": bool(image.get("is_ai_generated")),
    }


def write_outputs(
    matches: list[dict],
    report: list[dict],
    licenses: dict[int, dict],
    media_dir: Path,
    js_path: Path,
    report_path: Path,
) -> None:
    media_dir.mkdir(parents=True, exist_ok=True)
    credits: list[dict] = []
    downloaded: dict[str, Path] = {}
    for index, match in enumerate(matches, 1):
        image = match["image"]
        image_url = (image.get("thumbnails") or {}).get("small") or image.get("image")
        if not image_url:
            continue
        local_path = downloaded.get(image_url)
        if local_path is None:
            local_path = download_image(image_url, media_dir / f"wger-{image['id']}")
            downloaded[image_url] = local_path
        credits.append(attribution(match, local_path, licenses))
        print(f"[{index:02d}/{len(matches):02d}] {match['local']['name']} -> wger {match['remote']['id']}")
        time.sleep(0.08)

    active_files = {path.resolve() for path in downloaded.values()}
    for stale_path in media_dir.glob("wger-*.*"):
        if stale_path.resolve() not in active_files:
            stale_path.unlink()

    manifest = {
        "source": "wger.de",
        "api": API_URL,
        "entries": credits,
    }
    (media_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    media_map = {entry["key"]: entry for entry in credits}
    js = (
        "// Generated by scripts/import_wger_media.py. Do not edit manually.\n"
        f"window.EXERCISE_MEDIA = Object.freeze({json.dumps(media_map, ensure_ascii=False, separators=(',', ':'))});\n"
    )
    js_path.write_text(js, encoding="utf-8")
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--js-output", type=Path, default=DEFAULT_JS)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--threshold", type=float, default=92.0)
    parser.add_argument("--allow-automatic", action="store_true")
    parser.add_argument("--exclude-ai", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    remote = fetch_exercises()
    licenses = fetch_licenses()
    matches, report = choose_matches(
        catalog,
        remote,
        licenses,
        load_overrides(args.overrides),
        args.threshold,
        args.exclude_ai,
        args.allow_automatic,
    )
    unmatched = [entry for entry in report if entry["status"] == "unmatched"]
    print(f"wger exercises: {len(remote)}; selected: {len(matches)}; unmatched: {len(unmatched)}")
    if unmatched:
        print("Unmatched keys:", ", ".join(entry["key"] for entry in unmatched))
    if args.dry_run:
        args.report_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Candidate report written to {args.report_output}")
        return
    write_outputs(matches, report, licenses, DEFAULT_MEDIA_DIR, args.js_output, args.report_output)


if __name__ == "__main__":
    main()
