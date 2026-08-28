from datetime import datetime, timedelta

from src.models.user import User, db
from src.services.badges import backfill_historical_badges


def test_register_grants_pioneer_and_since_always(client):
    response_one = client.post("/api/register", json={"username": "badge-one", "password": "strong-password"})
    assert response_one.status_code == 201
    user_one = response_one.get_json()["user"]
    assert {badge["code"] for badge in user_one["badges"]} == {"pioneiro", "desde_sempre"}
    assert next(badge for badge in user_one["badges"] if badge["code"] == "pioneiro")["badge_rank"] == 1

    response_two = client.post("/api/register", json={"username": "badge-two", "password": "strong-password"})
    assert response_two.status_code == 201
    user_two = response_two.get_json()["user"]
    assert next(badge for badge in user_two["badges"] if badge["code"] == "pioneiro")["badge_rank"] == 2


def test_backfill_assigns_first_100_pioneers_and_respects_cutoff(app):
    with app.app_context():
        base = datetime(2026, 1, 1, 12, 0, 0)
        for index in range(101):
            user = User(username=f"backfill-{index}")
            user.set_password("strong-password")
            user.created_at = base + timedelta(minutes=index)
            db.session.add(user)

        late_user = User(username="backfill-late")
        late_user.set_password("strong-password")
        late_user.created_at = datetime(2027, 1, 1, 3, 0, 0)
        db.session.add(late_user)
        db.session.commit()

        granted = backfill_historical_badges()
        db.session.commit()

        pioneer_badges = [badge for badge in granted if badge and badge.badge_code == "pioneiro"]
        assert len(pioneer_badges) == 100

        first = db.session.query(User).filter_by(username="backfill-0").one()
        hundredth = db.session.query(User).filter_by(username="backfill-99").one()
        hundred_first = db.session.query(User).filter_by(username="backfill-100").one()
        late = db.session.query(User).filter_by(username="backfill-late").one()

        assert next(badge for badge in first.badges if badge.badge_code == "pioneiro").badge_rank == 1
        assert next(badge for badge in hundredth.badges if badge.badge_code == "pioneiro").badge_rank == 100
        assert not any(badge.badge_code == "pioneiro" for badge in hundred_first.badges)
        assert not any(badge.badge_code == "desde_sempre" for badge in late.badges)


def test_profile_badges_endpoint_lists_catalog_and_grants(client):
    register = client.post("/api/register", json={"username": "badge-profile", "password": "strong-password"})
    assert register.status_code == 201

    response = client.get("/api/profile/badges")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["catalog"]["pioneiro"]["title"] == "Pioneiro"
    assert any(badge["code"] == "desde_sempre" for badge in payload["badges"])


def test_profile_highlights_can_be_saved(client):
    register = client.post("/api/register", json={"username": "badge-highlights", "password": "strong-password"})
    assert register.status_code == 201
    token = register.get_json()["csrf_token"]

    response = client.put(
        "/api/profile/highlights",
        headers={"X-CSRF-Token": token},
        json={"items": [{"kind": "badge", "code": "pioneiro"}, {"kind": "badge", "code": "desde_sempre"}]},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert [item["position"] for item in payload["selected"]] == [1, 2]
    assert payload["selected"][0]["item"]["code"] == "pioneiro"

    achievements = client.get("/api/progress/achievements")
    assert achievements.status_code == 200
    catalog = achievements.get_json()
    assert catalog["highlight_limit"] == 3
    assert [item["item"]["code"] for item in catalog["selected"]] == [
        "pioneiro",
        "desde_sempre",
    ]
    assert {badge["code"] for badge in catalog["badges"]} == {
        "pioneiro",
        "desde_sempre",
    }

    hidden = next(item for item in catalog["items"] if item["code"] == "big_day")
    assert hidden["title"] == "Conquista oculta"
    assert hidden["progress"] is None
    assert hidden["unlocked"] is None

    first_step = next(item for item in catalog["items"] if item["code"] == "first_step")
    assert first_step["progress"] == {"current": 0, "target": 1, "percentage": 0}
