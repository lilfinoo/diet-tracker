from datetime import date, datetime, timedelta
from io import BytesIO

from PIL import Image

from src.legal import PROFESSIONAL_SHARING_VERSION
from src.models.user import (
    DietPlan,
    DietPlanMeal,
    ProfessionalReviewRequest,
    ProfessionalStudentRelationship,
    Subscription,
    User,
    UserProfile,
    WorkoutPlan,
    db,
)
from src.services.media_storage import MediaStorageError, prepare_avatar
from src.services.plan_management import plan_snapshot, snapshot_fingerprint
from tests.helpers import registration_payload


def register(client, username):
    response = client.post("/api/register", json=registration_payload(username))
    assert response.status_code == 201


def enable_professional(app, username, scope="both"):
    with app.app_context():
        user = User.query.filter_by(username=username).one()
        user.is_professional = True
        user.professional_scope = scope
        plan_code = {
            "workout": "professional_single",
            "diet": "professional_single",
            "both": "professional_complete",
        }[scope]
        db.session.add(Subscription(
            user_id=user.id,
            provider="asaas",
            external_subscription_id=f"sub-{username}",
            status="active",
            plan_code=plan_code,
            current_period_end=datetime.utcnow() + timedelta(days=30),
        ))
        db.session.commit()
        return user.id


def test_public_search_and_connections_require_opt_in_and_versioned_consent(app):
    student_client = app.test_client()
    professional_client = app.test_client()
    register(student_client, "network-student")
    register(professional_client, "network-coach")
    professional_id = enable_professional(app, "network-coach")

    assert student_client.get("/api/profiles/search?q=network-coach").get_json()["items"] == []
    assert student_client.post("/api/connections", json={
        "username": "network-coach",
        "direction": "request_professional",
        "data_sharing_consent": True,
        "sharing_consent_version": PROFESSIONAL_SHARING_VERSION,
    }).status_code == 404

    assert professional_client.put("/api/profile/public", json={"is_public": True}).status_code == 200
    results = student_client.get("/api/profiles/search?q=network-coach").get_json()["items"]
    assert [item["id"] for item in results] == [str(professional_id)]

    stale = student_client.post("/api/connections", json={
        "username": "network-coach",
        "direction": "request_professional",
        "data_sharing_consent": True,
        "sharing_consent_version": "old",
    })
    assert stale.status_code == 409
    created = student_client.post("/api/connections", json={
        "username": "network-coach",
        "direction": "request_professional",
        "data_sharing_consent": True,
        "sharing_consent_version": PROFESSIONAL_SHARING_VERSION,
    })
    assert created.status_code == 201
    assert professional_client.post(
        f"/api/connections/{created.get_json()['connection']['id']}/accept", json={}
    ).status_code == 200


def test_diet_adherence_requires_current_plan_and_all_meals_to_finalize(app, client):
    register(client, "adherence-user")
    with app.app_context():
        user = User.query.filter_by(username="adherence-user").one()
        profile = UserProfile(user_id=user.id, timezone="UTC")
        plan = DietPlan(user_id=user.id, status="published", source="manual", title="Plano atual")
        other = DietPlan(user_id=user.id, status="published", source="manual", title="Plano antigo")
        db.session.add_all([profile, plan, other])
        db.session.flush()
        meals = [
            DietPlanMeal(diet_plan_id=plan.id, day_of_week="Dia 1", meal_type="Almoço", description="A", order=1),
            DietPlanMeal(diet_plan_id=plan.id, day_of_week="Dia 1", meal_type="Jantar", description="B", order=2),
        ]
        db.session.add_all(meals)
        db.session.flush()
        profile.current_diet_plan_id = plan.id
        db.session.commit()
        plan_id = plan.id
        other_id = other.id
        meal_ids = [meal.id for meal in meals]

    today = date.today().isoformat()
    assert client.put(f"/api/diet_plans/{other_id}/adherence/{today}", json={
        "plan_day": "Dia 1", "meal_checkins": [],
    }).status_code == 409
    partial = client.put(f"/api/diet_plans/{plan_id}/adherence/{today}", json={
        "plan_day": "Dia 1",
        "meal_checkins": [{"diet_plan_meal_id": meal_ids[0], "status": "completed"}],
    })
    assert partial.status_code == 200
    incomplete = client.put(f"/api/diet_plans/{plan_id}/adherence/{today}", json={
        "plan_day": "Dia 1",
        "meal_checkins": [{"diet_plan_meal_id": meal_ids[0], "status": "completed"}],
        "finalize": True,
    })
    assert incomplete.status_code == 409
    completed = client.put(f"/api/diet_plans/{plan_id}/adherence/{today}", json={
        "plan_day": "Dia 1",
        "meal_checkins": [
            {"diet_plan_meal_id": meal_ids[0], "status": "completed"},
            {"diet_plan_meal_id": meal_ids[1], "status": "substituted", "note": "Equivalente"},
        ],
        "finalize": True,
    })
    assert completed.status_code == 200
    assert completed.get_json()["adherence"]["status"] == "completed"


def test_review_approved_as_is_requires_professional_and_preserves_fingerprint(app):
    student_client = app.test_client()
    professional_client = app.test_client()
    register(student_client, "review-student")
    register(professional_client, "review-coach")
    professional_id = enable_professional(app, "review-coach", "workout")
    assert professional_client.put("/api/profile/public", json={
        "is_public": True,
        "accepts_external_workout_reviews": True,
    }).status_code == 200
    with app.app_context():
        student = User.query.filter_by(username="review-student").one()
        plan = WorkoutPlan(
            user_id=student.id,
            status="published",
            source="manual",
            title="Treino para revisar",
            questionnaire_data={},
        )
        db.session.add(plan)
        db.session.commit()
        plan_id = plan.id

    created = student_client.post("/api/plan-reviews", json={
        "plan_type": "workout",
        "plan_id": plan_id,
        "target_mode": "specific",
        "professional_id": str(professional_id),
        "review_focus": ["structure"],
        "data_sharing_consent": True,
        "sharing_consent_version": PROFESSIONAL_SHARING_VERSION,
    })
    assert created.status_code == 201
    review_id = created.get_json()["review"]["id"]
    assert professional_client.post(f"/api/professional/plan-reviews/{review_id}/accept").status_code == 200
    assert professional_client.post(f"/api/professional/plan-reviews/{review_id}/start").status_code == 200
    completed = professional_client.post(f"/api/professional/plan-reviews/{review_id}/complete", json={
        "evaluation": "A estrutura está adequada para o objetivo informado.",
        "suggestions": [],
        "outcome": "approved_as_is",
    })
    assert completed.status_code == 200
    assert student_client.post(f"/api/plan-reviews/{review_id}/decision", json={"decision": "apply"}).status_code == 200
    badge = student_client.get(f"/api/workout_plans/{plan_id}/professional-review").get_json()
    assert badge["professional_review"]["professional"]["username"] == "review-coach"


def test_professional_cannot_request_review_of_own_plan(app, client):
    register(client, "self-review-coach")
    professional_id = enable_professional(app, "self-review-coach", "workout")
    assert client.put("/api/profile/public", json={
        "is_public": True,
        "accepts_external_workout_reviews": True,
    }).status_code == 200
    with app.app_context():
        plan = WorkoutPlan(
            user_id=professional_id,
            status="published",
            source="manual",
            title="Meu treino",
            questionnaire_data={},
        )
        db.session.add(plan)
        db.session.commit()
        plan_id = plan.id
    response = client.post("/api/plan-reviews", json={
        "plan_type": "workout",
        "plan_id": plan_id,
        "target_mode": "specific",
        "professional_id": str(professional_id),
        "review_focus": ["structure"],
        "data_sharing_consent": True,
        "sharing_consent_version": PROFESSIONAL_SHARING_VERSION,
    })
    assert response.status_code == 409


def test_review_proposal_is_hidden_from_regular_professional_plan_endpoints(app):
    professional_client = app.test_client()
    student_client = app.test_client()
    register(professional_client, "isolated-coach")
    register(student_client, "isolated-student")
    professional_id = enable_professional(app, "isolated-coach", "workout")
    with app.app_context():
        professional = db.session.get(User, professional_id)
        student = User.query.filter_by(username="isolated-student").one()
        relationship = ProfessionalStudentRelationship(
            professional_user_id=professional.id,
            student_user_id=student.id,
            status="active",
            invite_expires_at=datetime.utcnow() + timedelta(days=7),
            accepted_at=datetime.utcnow(),
            data_sharing_consent_version=PROFESSIONAL_SHARING_VERSION,
            data_sharing_consented_at=datetime.utcnow(),
        )
        source = WorkoutPlan(user_id=student.id, status="published", source="manual", title="Original")
        proposal = WorkoutPlan(
            user_id=student.id,
            author_user_id=professional.id,
            status="draft",
            source="manual",
            title="Proposta isolada",
        )
        db.session.add_all([relationship, source, proposal])
        db.session.flush()
        snapshot = plan_snapshot(source)
        review = ProfessionalReviewRequest(
            student_user_id=student.id,
            assigned_professional_user_id=professional.id,
            relationship_id=relationship.id,
            plan_type="workout",
            source_workout_plan_id=source.id,
            proposal_workout_plan_id=proposal.id,
            target_mode="linked",
            status="in_review",
            review_focus=["structure"],
            context_snapshot={},
            source_snapshot=snapshot,
            source_fingerprint=snapshot_fingerprint(snapshot),
            sharing_consent_version=PROFESSIONAL_SHARING_VERSION,
            sharing_consented_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        db.session.add(review)
        db.session.commit()
        student_id = student.id
        proposal_id = proposal.id

    response = professional_client.get(
        f"/api/professional/students/{student_id}/workout-plans/{proposal_id}"
    )
    assert response.status_code == 404


def test_workout_only_professional_does_not_receive_diet_plan_summary(app):
    professional_client = app.test_client()
    student_client = app.test_client()
    register(professional_client, "scope-coach")
    register(student_client, "scope-student")
    professional_id = enable_professional(app, "scope-coach", "workout")
    with app.app_context():
        student = User.query.filter_by(username="scope-student").one()
        db.session.add_all([
            ProfessionalStudentRelationship(
                professional_user_id=professional_id,
                student_user_id=student.id,
                status="active",
                invite_expires_at=datetime.utcnow() + timedelta(days=7),
                accepted_at=datetime.utcnow(),
                data_sharing_consent_version=PROFESSIONAL_SHARING_VERSION,
                data_sharing_consented_at=datetime.utcnow(),
            ),
            DietPlan(user_id=student.id, status="published", source="manual", title="Dieta privada ao escopo"),
        ])
        db.session.commit()
        student_id = student.id

    payload = professional_client.get(f"/api/professional/students/{student_id}").get_json()
    assert payload["latest_diet_plan"] is None
    assert "recent_diet_entries" not in payload
    assert "recent_diet_adherence" not in payload


def test_avatar_processing_strips_metadata_and_rejects_excessive_dimensions():
    source = BytesIO()
    Image.new("RGB", (32, 32), "red").save(source, "JPEG", exif=b"Exif\x00\x00metadata")
    processed = prepare_avatar(BytesIO(source.getvalue()))
    result = Image.open(BytesIO(processed))
    assert result.format == "WEBP"
    assert not result.getexif()

    oversized = BytesIO()
    Image.new("1", (5000, 4000)).save(oversized, "PNG")
    try:
        prepare_avatar(BytesIO(oversized.getvalue()))
    except MediaStorageError as error:
        assert "16 megapixels" in str(error)
    else:
        raise AssertionError("oversized image should be rejected")
