import json
import os
import ssl
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import certifi
from flask import current_app
from src.services.workoutx_classification import movement_pattern


BASE_URL = "https://api.workoutxapp.com/v1"
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

REVIEW_QUEUE = (
    "puxada_com_elastico", "flexao_joelhos_deslizante", "flexao_nordica",
    "extensao_joelho_elastico", "extensao_terminal_joelho", "panturrilha_em_pe_maquina",
    "panturrilha_com_halteres", "elevacao_lateral_elastico", "elevacao_lateral_inclinada",
    "abdominal_reverso", "abdominal_na_polia", "abdominal_na_bola",
)
REVIEW_SEARCH_QUERIES = {
    "puxada_com_elastico": "band pulldown",
    "flexao_joelhos_deslizante": "sliding leg curl",
    "flexao_nordica": "nordic hamstring curl",
    "extensao_joelho_elastico": "band knee extension",
    "extensao_terminal_joelho": "terminal knee extension band",
    "panturrilha_em_pe_maquina": "standing calf raise machine",
    "panturrilha_com_halteres": "dumbbell calf raise",
    "elevacao_lateral_elastico": "band lateral raise",
    "elevacao_lateral_inclinada": "incline dumbbell lateral raise",
    "abdominal_reverso": "reverse crunch",
    "abdominal_na_polia": "cable crunch",
    "abdominal_na_bola": "stability ball crunch",
}
SELECTION_QUOTAS = {
    "chest": 45,
    "back": 65,
    "shoulders": 40,
    "biceps": 25,
    "triceps": 25,
    "forearms": 15,
    "quads": 35,
    "glutes": 30,
    "hamstrings": 30,
    "calves": 20,
    "core": 35,
}
TARGET_GROUPS = {
    "pectorals": "chest",
    "lats": "back",
    "upper back": "back",
    "traps": "back",
    "spine": "back",
    "delts": "shoulders",
    "biceps": "biceps",
    "triceps": "triceps",
    "forearms": "forearms",
    "quads": "quads",
    "glutes": "glutes",
    "hamstrings": "hamstrings",
    "calves": "calves",
    "abs": "core",
    "serratus anterior": "core",
}
EQUIPMENT_PRIORITY = {
    "barbell": 6,
    "olympic barbell": 6,
    "dumbbell": 6,
    "cable": 6,
    "leverage machine": 5,
    "smith machine": 5,
    "body weight": 5,
    "ez barbell": 4,
    "kettlebell": 4,
    "resistance band": 3,
}
COMMON_MOVEMENT_MARKERS = (
    "lateral raise", "side raise", "lateral arm raise", "leg press", "press machine",
    "leg extension", "knee extension", "leg curl", "hamstring curl", "bench press",
    "chest press", "shoulder press", "overhead press", "military press", "pulldown",
    "pull down", "row", "bicep curl", "barbell curl", "triceps extension", "calf raise",
)
LOW_PRIORITY_MARKERS = (
    "stretch", "jump", "bosu", "snatch", "clean and", "behind neck", "behind head",
    "guillotine", "boxing", "skier",
)


class WorkoutXServiceError(Exception):
    """Raised when WorkoutX cannot provide a usable exercise GIF."""


def media_mapping():
    path = Path(current_app.config["WORKOUTX_MEDIA_MAPPING_PATH"])
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkoutXServiceError("WorkoutX media mapping is invalid") from error
    return data if isinstance(data, dict) else {}


def approved_media(catalog_key):
    # Runtime approvals live in the database because Render's filesystem is ephemeral.
    from src.models.user import ExerciseMediaReview

    review = ExerciseMediaReview.query.filter_by(catalog_key=catalog_key).first()
    if review is not None:
        if review.status != "approved" or not review.provider_id:
            return None
        return {
            "provider_id": review.provider_id,
            "provider_name": review.provider_name,
            "provider_equipment": review.provider_equipment or "",
        }
    entry = media_mapping().get(catalog_key)
    return entry if isinstance(entry, dict) and entry.get("provider_id") else None


def _request(url, max_bytes=None):
    api_key = current_app.config.get("WORKOUTX_API_KEY")
    if not api_key:
        raise WorkoutXServiceError("WORKOUTX_API_KEY is not configured")
    request = Request(url, headers={"X-WorkoutX-Key": api_key})
    try:
        with urlopen(
            request,
            timeout=current_app.config["WORKOUTX_TIMEOUT"],
            context=SSL_CONTEXT,
        ) as response:
            limit = max_bytes or current_app.config["WORKOUTX_MAX_RESPONSE_BYTES"]
            body = response.read(limit + 1)
            if len(body) > limit:
                raise WorkoutXServiceError("WorkoutX response is too large")
            return body
    except HTTPError as error:
        raise WorkoutXServiceError(f"WorkoutX request failed with status {error.code}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise WorkoutXServiceError("WorkoutX is unavailable") from error


def _provider_id(value):
    value = str(value or "")
    if not value.isdigit() or len(value) > 32:
        raise WorkoutXServiceError("Invalid WorkoutX exercise ID")
    return value


def search_exercises(query):
    response = _request(f"{BASE_URL}/exercises/name/{quote(query)}?limit=8")
    try:
        data = json.loads(response)
    except json.JSONDecodeError as error:
        raise WorkoutXServiceError("WorkoutX returned invalid exercise data") from error
    entries = data.get("data", data) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise WorkoutXServiceError("WorkoutX returned an unexpected exercise response")
    results = []
    for item in entries:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        try:
            provider_id = _provider_id(item["id"])
        except WorkoutXServiceError:
            continue
        results.append({
            "id": provider_id,
            "name": str(item.get("name", ""))[:200],
            "equipment": str(item.get("equipment", ""))[:100],
        })
    return results


def _selection_group(exercise):
    return TARGET_GROUPS.get(str(exercise.get("target", "")).strip().lower())


def _movement_pattern(exercise):
    return movement_pattern(exercise)


def _equipment_family(exercise):
    equipment = str(exercise.get("equipment", "")).strip().lower()
    if "barbell" in equipment:
        return "barbell"
    if "dumbbell" in equipment:
        return "dumbbell"
    if "cable" in equipment:
        return "cable"
    if "machine" in equipment:
        return equipment
    return equipment or "other"


def _selection_score(exercise):
    equipment = str(exercise.get("equipment", "")).strip().lower()
    name = str(exercise.get("name", "")).lower()
    score = (
        EQUIPMENT_PRIORITY.get(equipment, 0)
        + (3 if exercise.get("gifUrl") else 0)
        + (2 if exercise.get("instructions") else 0)
        + (2 if exercise.get("secondaryMuscles") else 0)
        + (2 if exercise.get("mechanic") == "compound" else 0)
        + (1 if exercise.get("difficulty") else 0)
        + (1 if not any(value in name for value in ("stretch", "assisted", "lying")) else 0)
    )
    if any(marker in name for marker in COMMON_MOVEMENT_MARKERS):
        score += 8
    if any(marker in name for marker in LOW_PRIORITY_MARKERS):
        score -= 20
    return score


def select_exercises(exercises):
    candidates = [exercise for exercise in exercises if _selection_group(exercise)]
    candidates.sort(key=lambda exercise: (
        -_selection_score(exercise),
        _movement_pattern(exercise),
        str(exercise.get("name", "")).lower(),
        str(exercise["id"]),
    ))
    selected = []
    class_counts = {}

    for group, quota in SELECTION_QUOTAS.items():
        group_count = 0
        for exercise in candidates:
            if _selection_group(exercise) != group or group_count >= quota:
                continue
            exercise_class = (
                group,
                _movement_pattern(exercise),
                str(exercise.get("mechanic", "")).lower(),
                str(exercise.get("force", "")).lower(),
                _equipment_family(exercise),
            )
            if class_counts.get(exercise_class, 0) >= 3:
                continue
            selected.append(exercise)
            class_counts[exercise_class] = class_counts.get(exercise_class, 0) + 1
            group_count += 1

    return selected


def _preview_directory(directory=None):
    return Path(directory) if directory else Path(current_app.instance_path) / "workoutx-preview"


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}-", suffix=".tmp")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
            json.dump(payload, temporary_file, ensure_ascii=False)
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _preview_pages(directory):
    pages = []
    expected_offset = 0
    for path in sorted((directory / "pages").glob("offset-*.json")):
        try:
            page = json.loads(path.read_text(encoding="utf-8"))
            offset = int(page["offset"])
            count = int(page["count"])
            data = page["data"]
            ids = page["exercise_ids"]
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise WorkoutXServiceError("WorkoutX preview cache is invalid") from error
        if offset != expected_offset or count != len(data) or [str(item.get("id")) for item in data] != ids:
            raise WorkoutXServiceError("WorkoutX preview cache is incomplete")
        for exercise in data:
            if not isinstance(exercise, dict):
                raise WorkoutXServiceError("WorkoutX preview cache is invalid")
            _provider_id(exercise.get("id"))
        pages.append(page)
        expected_offset += count
    return pages


def _write_preview_manifest(directory, pages, total):
    _write_json(directory / "manifest.json", {
        "limit": 10,
        "total": total,
        "pages": [{
            "offset": page["offset"],
            "count": page["count"],
            "exercise_ids": page["exercise_ids"],
            "collected_at": page["collected_at"],
        } for page in pages],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


def collect_preview_exercises(directory=None, pause_seconds=2):
    directory = _preview_directory(directory)
    pages = _preview_pages(directory)
    total = None
    manifest_path = directory / "manifest.json"
    if manifest_path.is_file():
        try:
            total = int(json.loads(manifest_path.read_text(encoding="utf-8"))["total"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise WorkoutXServiceError("WorkoutX preview manifest is invalid") from error

    offset = sum(page["count"] for page in pages)
    calls = 0
    while total is None or offset < total:
        if offset:
            time.sleep(pause_seconds)
        response = _request(f"{BASE_URL}/exercises?{urlencode({'limit': 10, 'offset': offset})}")
        calls += 1
        try:
            payload = json.loads(response)
            batch = payload["data"]
            page_total = int(payload["total"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise WorkoutXServiceError("WorkoutX returned invalid exercise data") from error
        if not isinstance(batch, list) or page_total < 0 or (total is not None and page_total != total):
            raise WorkoutXServiceError("WorkoutX returned invalid pagination data")
        total = page_total
        if not batch:
            break
        for exercise in batch:
            if not isinstance(exercise, dict):
                raise WorkoutXServiceError("WorkoutX returned invalid exercise data")
            _provider_id(exercise.get("id"))
        page = {
            "offset": offset,
            "count": len(batch),
            "exercise_ids": [str(exercise["id"]) for exercise in batch],
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "data": batch,
        }
        _write_json(directory / "pages" / f"offset-{offset:04d}.json", page)
        pages.append(page)
        _write_preview_manifest(directory, pages, total)
        offset += len(batch)

    if total is None or offset != total:
        raise WorkoutXServiceError("WorkoutX preview cache is incomplete")
    return {"pages_downloaded": calls, "pages_cached": len(pages), "total": total}


def preview_exercises(directory=None):
    pages = _preview_pages(_preview_directory(directory))
    exercises = [exercise for page in pages for exercise in page["data"]]
    if not exercises:
        raise WorkoutXServiceError("WorkoutX preview cache is empty")
    return exercises


def preview_catalog_comparison(directory=None):
    from src.models.user import WorkoutXExercise

    proposed = select_exercises(preview_exercises(directory))
    current = [item.data for item in WorkoutXExercise.query.all()]
    current_ids = {str(item["id"]) for item in current}
    proposed_ids = {str(item["id"]) for item in proposed}
    def count(items, key):
        values = {}
        for item in items:
            value = key(item)
            values[value] = values.get(value, 0) + 1
        return dict(sorted(values.items()))
    def matching(items, markers):
        return sum(any(marker in str(item.get("name", "")).lower() for marker in markers) for item in items)
    return {
        "selected": len(proposed),
        "added": len(proposed_ids - current_ids),
        "removed": len(current_ids - proposed_ids),
        "groups": count(proposed, lambda item: _selection_group(item) or "other"),
        "equipment": count(proposed, lambda item: str(item.get("equipment") or "unknown")),
        "priority_counts": {
            "lateral_raise": matching(proposed, ("lateral raise", "side raise", "lateral arm raise")),
            "leg_press": matching(proposed, ("leg press", "press machine")),
            "leg_extension": matching(proposed, ("leg extension", "knee extension")),
        },
        "important_added": [
            item["name"] for item in proposed
            if str(item["id"]) not in current_ids
            and any(marker in str(item.get("name", "")).lower() for marker in COMMON_MOVEMENT_MARKERS)
        ],
        "low_priority_removed": [
            item["name"] for item in current
            if str(item["id"]) not in proposed_ids
            and any(marker in str(item.get("name", "")).lower() for marker in LOW_PRIORITY_MARKERS)
        ],
    }


def apply_preview_catalog(directory=None):
    from src.models.user import WorkoutXExercise, db

    selected = select_exercises(preview_exercises(directory))
    if not selected:
        raise WorkoutXServiceError("WorkoutX preview selection is empty")
    WorkoutXExercise.query.delete()
    db.session.add_all(
        WorkoutXExercise(provider_id=_provider_id(exercise["id"]), data=exercise)
        for exercise in selected
    )
    db.session.commit()
    return len(selected)


def _exercise_pages(limit=10):
    offset = 0
    total = None
    received = 0

    while total is None or offset < total:
        if offset:
            time.sleep(2)
        response = _request(f"{BASE_URL}/exercises?{urlencode({'limit': limit, 'offset': offset})}")
        try:
            payload = json.loads(response)
        except json.JSONDecodeError as error:
            raise WorkoutXServiceError("WorkoutX returned invalid exercise data") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise WorkoutXServiceError("WorkoutX returned an unexpected exercise response")

        batch = payload["data"]
        for exercise in batch:
            if not isinstance(exercise, dict) or not exercise.get("id"):
                raise WorkoutXServiceError("WorkoutX returned an exercise without an ID")
            _provider_id(exercise["id"])

        if total is None:
            try:
                total = int(payload["total"])
            except (KeyError, TypeError, ValueError) as error:
                raise WorkoutXServiceError("WorkoutX returned invalid pagination data") from error
            if total < 0:
                raise WorkoutXServiceError("WorkoutX returned invalid pagination data")
        if not batch:
            break
        received += len(batch)
        yield batch
        offset += len(batch)

    if total is not None and received != total:
        raise WorkoutXServiceError("WorkoutX returned an incomplete exercise catalog")


def fetch_all_exercises(limit=10):
    exercises = [exercise for batch in _exercise_pages(limit) for exercise in batch]
    return exercises


def import_exercises():
    from src.models.user import WorkoutXExercise, db

    selected = select_exercises(fetch_all_exercises())
    WorkoutXExercise.query.delete()
    db.session.add_all(
        WorkoutXExercise(provider_id=_provider_id(exercise["id"]), data=exercise)
        for exercise in selected
    )
    db.session.commit()
    return len(selected)


def get_exercise(provider_id):
    provider_id = _provider_id(provider_id)
    try:
        data = json.loads(_request(f"{BASE_URL}/exercises/exercise/{provider_id}"))
    except json.JSONDecodeError as error:
        raise WorkoutXServiceError("WorkoutX returned invalid exercise data") from error
    if not isinstance(data, dict) or not data.get("id") or not data.get("gifUrl"):
        raise WorkoutXServiceError("WorkoutX did not return a usable exercise")
    return data


def get_cached_gif(catalog_key, provider_id):
    provider_id = _provider_id(provider_id)
    cache_dir = Path(current_app.config["WORKOUTX_CACHE_DIR"])
    cache_path = cache_dir / f"{catalog_key}-{provider_id}.gif"
    if cache_path.is_file() and cache_path.stat().st_size:
        return cache_path

    gif = _request(
        f"{BASE_URL}/gifs/{provider_id}",
        max_bytes=current_app.config["WORKOUTX_MAX_RESPONSE_BYTES"],
    )
    if not gif.startswith((b"GIF87a", b"GIF89a")):
        raise WorkoutXServiceError("WorkoutX did not return a GIF")
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=cache_dir,
            prefix=f".{catalog_key}-{provider_id}-",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as temporary_file:
                temporary_file.write(gif)
            temporary_path.replace(cache_path)
        finally:
            temporary_path.unlink(missing_ok=True)
    except OSError as error:
        raise WorkoutXServiceError("WorkoutX GIF could not be cached") from error
    return cache_path
