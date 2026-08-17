import json
import os
import ssl
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import certifi
from flask import current_app


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
    except URLError as error:
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
