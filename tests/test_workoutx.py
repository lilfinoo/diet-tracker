from src.services import workoutx
from io import BytesIO
from urllib.error import HTTPError

from src.models.user import ExerciseMediaReview, User, WorkoutXExercise, WorkoutXGif, db
from tests.helpers import registration_payload


class _Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


def test_workoutx_downloads_a_gif_once(app, tmp_path, monkeypatch):
    calls = []

    def fake_urlopen(request, **kwargs):
        calls.append(request.full_url)
        return _Response(b"GIF89aexercise-animation")

    monkeypatch.setattr(workoutx, "urlopen", fake_urlopen)
    with app.app_context():
        app.config.update(
            WORKOUTX_API_KEY="wx_test",
            WORKOUTX_CACHE_DIR=tmp_path,
        )
        first = workoutx.get_cached_gif("agachamento_livre", "0201")
        second = workoutx.get_cached_gif("workoutx:0201", "0201")

    assert first == second
    assert first.read_bytes() == b"GIF89aexercise-animation"
    assert calls == ["https://api.workoutxapp.com/v1/gifs/0201"]


def test_examples_use_only_workoutx_gifs(app):
    with app.app_context():
        assert workoutx.approved_media("elevacao_lateral_cabo")["provider_id"] == "0178"
        assert workoutx.approved_media("abdominal_na_polia")["provider_id"] == "0175"
        assert workoutx.approved_media("rosca_martelo")["provider_id"] == "0313"


def test_workoutx_restores_a_gif_from_persistent_cache(app, tmp_path, monkeypatch):
    monkeypatch.setattr("src.services.media_storage.get_exercise_gif", lambda provider_id: b"GIF89apersistent")
    monkeypatch.setattr("src.services.media_storage.configured", lambda: True)
    monkeypatch.setattr(workoutx, "_request", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("API called")))
    with app.app_context():
        app.config["WORKOUTX_CACHE_DIR"] = tmp_path
        path = workoutx.get_cached_gif("workoutx:0289", "0289")

    assert path.read_bytes() == b"GIF89apersistent"


def test_workoutx_persists_a_gif_in_the_database_cache(app, tmp_path, monkeypatch):
    calls = []

    def fake_request(url, **_kwargs):
        calls.append(url)
        return b"GIF89adatabase-cache"

    monkeypatch.setattr(workoutx, "_request", fake_request)
    with app.app_context():
        app.config["WORKOUTX_CACHE_DIR"] = tmp_path
        first = workoutx.get_cached_gif("workoutx:0289", "0289")
        first.unlink()
        second = workoutx.get_cached_gif("workoutx:0289", "0289")

    assert first == second
    assert second.read_bytes() == b"GIF89adatabase-cache"
    assert calls == ["https://api.workoutxapp.com/v1/gifs/0289"]


def test_workoutx_429_starts_a_fast_failure_cooldown(app, tmp_path, monkeypatch):
    calls = []

    def rate_limited(request, **_kwargs):
        calls.append(request.full_url)
        raise HTTPError(request.full_url, 429, "rate limited", {"Retry-After": "30"}, None)

    monkeypatch.setattr(workoutx, "urlopen", rate_limited)
    monkeypatch.setattr(workoutx, "GIF_DOWNLOAD_BLOCKED_UNTIL", 0.0)
    with app.app_context():
        app.config.update(WORKOUTX_API_KEY="wx_test", WORKOUTX_CACHE_DIR=tmp_path)
        for provider_id in ("0201", "0202"):
            try:
                workoutx.get_cached_gif(f"workoutx:{provider_id}", provider_id)
            except workoutx.WorkoutXServiceError as error:
                assert error.retry_after > 0
            else:
                raise AssertionError("rate-limited GIF unexpectedly loaded")

    assert calls == ["https://api.workoutxapp.com/v1/gifs/0201"]


def test_workoutx_search_discards_unsafe_provider_ids(app, monkeypatch):
    monkeypatch.setattr(
        workoutx,
        "_request",
        lambda url: b'{"data":[{"id":"123","name":"Safe"},{"id":"1\\\" onclick=\\\"alert(1)","name":"Unsafe"}]}',
    )
    with app.app_context():
        assert workoutx.search_exercises("press") == [
            {"id": "123", "name": "Safe", "equipment": ""}
        ]


def test_workoutx_imports_every_page_and_updates_existing_records(app, monkeypatch):
    responses = [
        b'{"total":3,"count":2,"data":[{"id":"0001","name":"First","target":"abs"},{"id":"0002","name":"Second","target":"biceps"}]}',
        b'{"total":3,"count":1,"data":[{"id":"0003","name":"Third","target":"quads"}]}',
    ]
    monkeypatch.setattr(workoutx, "_request", lambda url: responses.pop(0))

    with app.app_context():
        db.session.add(WorkoutXExercise(provider_id="0001", data={"id": "0001", "name": "Old"}))
        db.session.commit()

        assert workoutx.import_exercises() == 3
        assert WorkoutXExercise.query.count() == 3
        assert db.session.get(WorkoutXExercise, "0001").data["name"] == "First"


def test_catalog_selection_prioritizes_common_movements():
    selected = workoutx.select_exercises([
        {"id": "1", "name": "Bosu Squat", "target": "quads", "equipment": "Bosu Ball"},
        {"id": "2", "name": "Leg Press Machine", "target": "quads", "equipment": "Leverage Machine"},
    ])

    assert [item["id"] for item in selected] == ["2", "1"]


def test_preview_collection_resumes_without_refetching_saved_pages(app, tmp_path, monkeypatch):
    responses = [
        b'{"total":2,"data":[{"id":"0001","name":"First"}]}',
        b'{"total":2,"data":[{"id":"0002","name":"Second"}]}',
    ]
    calls = []

    def request(url):
        calls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(workoutx, "_request", request)
    with app.app_context():
        first = workoutx.collect_preview_exercises(tmp_path, pause_seconds=0)
        second = workoutx.collect_preview_exercises(tmp_path, pause_seconds=0)

    assert first == {"pages_downloaded": 2, "pages_cached": 2, "total": 2}
    assert second == {"pages_downloaded": 0, "pages_cached": 2, "total": 2}
    assert calls == [
        "https://api.workoutxapp.com/v1/exercises?limit=10&offset=0",
        "https://api.workoutxapp.com/v1/exercises?limit=10&offset=1",
    ]


def test_preview_application_replaces_the_active_catalog(app, monkeypatch):
    monkeypatch.setattr(workoutx, "preview_exercises", lambda directory=None: [
        {"id": "0001", "name": "First", "target": "abs"},
        {"id": "0002", "name": "Second", "target": "biceps"},
    ])
    with app.app_context():
        db.session.add(WorkoutXExercise(provider_id="old", data={"id": "old", "name": "Old"}))
        db.session.commit()

        assert workoutx.apply_preview_catalog() == 2
        assert [item.provider_id for item in WorkoutXExercise.query.order_by(WorkoutXExercise.provider_id)] == [
            "0001", "0002"
        ]


def test_workoutx_rejects_oversized_response(app, monkeypatch):
    monkeypatch.setattr(
        workoutx,
        "urlopen",
        lambda request, **kwargs: _Response(b"GIF89a-too-large"),
    )
    with app.app_context():
        app.config.update(WORKOUTX_API_KEY="wx_test", WORKOUTX_MAX_RESPONSE_BYTES=8)
        try:
            workoutx._request("https://example.test/gif")
        except workoutx.WorkoutXServiceError as error:
            assert str(error) == "WorkoutX response is too large"
        else:
            raise AssertionError("oversized WorkoutX response was accepted")


def test_exercise_media_requires_login(client):
    assert client.get("/api/exercise-media/agachamento_livre").status_code == 401


def test_workoutx_catalog_key_uses_its_own_gif_without_manual_review(app):
    with app.app_context():
        db.session.add(WorkoutXExercise(provider_id="0289", data={
            "id": "0289", "name": "Dumbbell Bench Press",
            "equipment": "Dumbbell", "gifUrl": "https://example.test/0289.gif",
        }))
        db.session.commit()

        assert workoutx.approved_media("workoutx:0289") == {
            "provider_id": "0289",
            "provider_name": "Dumbbell Bench Press",
            "provider_equipment": "Dumbbell",
        }


def test_authenticated_user_can_serve_a_direct_workoutx_gif(app, client, tmp_path, monkeypatch):
    assert client.post("/api/register", json=registration_payload("athlete")).status_code == 201
    media_path = tmp_path / "0289.gif"
    media_path.write_bytes(b"GIF89adirect")
    monkeypatch.setattr("src.routes.profile_routes.get_cached_gif", lambda *args: media_path)
    with app.app_context():
        db.session.add(WorkoutXExercise(provider_id="0289", data={
            "id": "0289", "name": "Dumbbell Bench Press",
            "equipment": "Dumbbell", "gifUrl": "https://example.test/0289.gif",
        }))
        db.session.commit()

    response = client.get("/api/exercise-media/workoutx:0289")
    assert response.status_code == 200
    assert response.data == b"GIF89adirect"


def test_exercise_media_exposes_rate_limit_cooldown(app, client, monkeypatch):
    assert client.post("/api/register", json=registration_payload("rate-limited-athlete")).status_code == 201
    monkeypatch.setattr(
        "src.routes.profile_routes.get_cached_gif",
        lambda *_args: (_ for _ in ()).throw(workoutx.WorkoutXServiceError("limited", retry_after=30)),
    )
    with app.app_context():
        db.session.add(WorkoutXExercise(provider_id="0289", data={
            "id": "0289", "name": "Dumbbell Bench Press",
            "equipment": "Dumbbell", "gifUrl": "https://example.test/0289.gif",
        }))
        db.session.commit()

    response = client.get("/api/exercise-media/workoutx:0289")
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    assert response.headers["Cache-Control"] == "private, max-age=60"


def test_admin_can_import_a_workoutx_gif_directly_into_database(app, client):
    assert client.post("/api/register", json=registration_payload("gif-admin")).status_code == 201
    with app.app_context():
        user = User.query.filter_by(username="gif-admin").one()
        user.is_admin = True
        db.session.add(WorkoutXExercise(provider_id="0289", data={
            "id": "0289", "name": "Dumbbell Bench Press",
            "equipment": "Dumbbell", "gifUrl": "https://example.test/0289.gif",
        }))
        db.session.commit()

    response = client.post(
        "/api/admin/exercise-media/cache/0289",
        data={"gif": (BytesIO(b"GIF89aimported"), "review-0289-0289.gif")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    with app.app_context():
        assert db.session.get(WorkoutXGif, "0289").content == b"GIF89aimported"


def test_exact_legacy_alias_is_automatic_but_equipment_mismatch_is_doubt(app):
    exercise = {
        "name": "Supino reto com halteres",
        "aliases": ["dumbbell bench press"],
        "equipment": "dumbbell",
    }
    with app.app_context():
        db.session.add(WorkoutXExercise(provider_id="0289", data={
            "id": "0289", "name": "Dumbbell Bench Press",
            "equipment": "Dumbbell", "gifUrl": "https://example.test/0289.gif",
        }))
        db.session.commit()

        assert workoutx.automatic_legacy_media(exercise)["provider_id"] == "0289"
        assert not workoutx.review_mapping_is_doubt(exercise, {
            "name": "Dumbbell Bench Press", "equipment": "Dumbbell",
        })
        assert workoutx.review_mapping_is_doubt(exercise, {
            "name": "Barbell Bench Press", "equipment": "Barbell",
        })


def test_admin_can_approve_and_serve_exercise_media(app, client, tmp_path, monkeypatch):
    app.config["WORKOUTX_MEDIA_MAPPING_PATH"] = tmp_path / "media.json"
    assert client.post("/api/register", json=registration_payload("admin")).status_code == 201
    with app.app_context():
        User.query.filter_by(username="admin").one().is_admin = True
        db.session.commit()

    media_path = tmp_path / "agachamento_livre.gif"
    media_path.write_bytes(b"GIF89aapproved")
    monkeypatch.setattr("src.routes.admin_routes.get_exercise", lambda provider_id: {
        "id": provider_id, "name": "Barbell Squat", "equipment": "Barbell", "gifUrl": "https://example.test/gif",
    })
    monkeypatch.setattr("src.routes.admin_routes.get_cached_gif", lambda *args: media_path)
    monkeypatch.setattr("src.routes.profile_routes.get_cached_gif", lambda *args: media_path)

    with app.app_context():
        db.session.add(WorkoutXExercise(provider_id="0201", data={
            "id": "0201", "name": "Barbell Squat", "equipment": "Barbell",
            "gifUrl": "https://example.test/gif",
        }))
        db.session.commit()

    response = client.put("/api/admin/exercise-media/agachamento_livre", json={"provider_id": "0201"})
    assert response.status_code == 200
    assert response.get_json()["review"]["provider_name"] == "Barbell Squat"
    assert not app.config["WORKOUTX_MEDIA_MAPPING_PATH"].exists()
    assert client.get("/api/exercise-media/agachamento_livre").status_code == 200
    with app.app_context():
        assert db.session.get(ExerciseMediaReview, "agachamento_livre").status == "approved"
