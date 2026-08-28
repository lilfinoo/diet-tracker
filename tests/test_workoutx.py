from src.services import workoutx
from src.models.user import ExerciseMediaReview, User, db


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
        second = workoutx.get_cached_gif("agachamento_livre", "0201")

    assert first == second
    assert first.read_bytes() == b"GIF89aexercise-animation"
    assert calls == ["https://api.workoutxapp.com/v1/gifs/0201"]


def test_workoutx_review_queue_has_twelve_exercises():
    assert len(workoutx.REVIEW_QUEUE) == 12


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


def test_admin_can_approve_and_serve_exercise_media(app, client, tmp_path, monkeypatch):
    app.config["WORKOUTX_MEDIA_MAPPING_PATH"] = tmp_path / "media.json"
    assert client.post("/api/register", json={"username": "admin", "password": "strong-password"}).status_code == 201
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

    response = client.put("/api/admin/exercise-media/agachamento_livre", json={"provider_id": "0201"})
    assert response.status_code == 200
    assert response.get_json()["review"]["provider_name"] == "Barbell Squat"
    assert not app.config["WORKOUTX_MEDIA_MAPPING_PATH"].exists()
    assert client.get("/api/exercise-media/agachamento_livre").status_code == 200
    with app.app_context():
        assert db.session.get(ExerciseMediaReview, "agachamento_livre").status == "approved"
