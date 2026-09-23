from datetime import datetime, timedelta
from uuid import uuid4

from src.models.user import (
    AITask,
    DelegatedActionAudit,
    DietPlan,
    ProfessionalStudentRelationship,
    Subscription,
    User,
    UserProfile,
    WorkoutPlan,
    db,
)
from src.services.ai_queue import execute_ai_job
from tests.helpers import registration_payload
from src.legal import PROFESSIONAL_SHARING_VERSION


SHARING_CONSENT = {
    "data_sharing_consent": True,
    "data_sharing_consent_version": PROFESSIONAL_SHARING_VERSION,
}


def register(client, username):
    return client.post("/api/register", json=registration_payload(username))


def enable_professional(app, username, premium=False):
    with app.app_context():
        user = User.query.filter_by(username=username).one()
        user.is_professional = True
        user.is_premium = premium
        user.professional_scope = "both"
        db.session.add(Subscription(
            user_id=user.id,
            provider="asaas",
            external_subscription_id=f"sub-{username}",
            status="active",
            plan_code="professional_complete",
            current_period_end=datetime.utcnow() + timedelta(days=30),
        ))
        db.session.commit()


def link_student(app, professional_client, student_client, professional_name="trainer", student_name="student"):
    register(professional_client, professional_name)
    enable_professional(app, professional_name)
    invitation = professional_client.post("/api/professional/invitations", json={}).get_json()
    register(student_client, student_name)
    accepted = student_client.post(f"/api/invitations/{invitation['token']}/accept", json=SHARING_CONSENT)
    assert accepted.status_code == 200
    with app.app_context():
        return User.query.filter_by(username=student_name).one().id


def workout_questionnaire():
    return {
        "goal": "hypertrophy",
        "experience_level": "beginner",
        "days_per_week": 2,
        "split_type": "full_body",
        "session_duration": 45,
        "equipment": ["full_gym"],
        "limitations": "",
        "priorities": "",
        "avoid_exercises": "",
    }


def generated_workout():
    day_keys = [
        ["leg_press_45", "supino_maquina", "remada_maquina", "prancha_frontal"],
        ["agachamento_goblet", "supino_reto_halteres", "remada_unilateral_halter", "dead_bug"],
    ]
    day_slot_ids = [
        ["FB_1_coverage_1", "FB_1_coverage_2", "FB_1_coverage_3", "FB_1_complement_4"],
        ["FB_2_coverage_1", "FB_2_coverage_2", "FB_2_coverage_3", "FB_2_complement_4"],
    ]
    return {
        "type": "workout_plan",
        "title": "Treino do aluno",
        "description": "Plano revisável.",
        "days": [{
            "focus": "Corpo inteiro",
            "exercises": [{
                "slot_id": day_slot_ids[day_index][exercise_index],
                "catalog_key": key,
                "sets": 3,
                "reps": "8-12",
                "weight": "Moderada",
                "rest_seconds": 60,
                "effort_guidance": "2 repetições em reserva",
                "notes": "Execução controlada",
            } for exercise_index, key in enumerate(keys)],
        } for day_index, keys in enumerate(day_keys)],
    }


def diet_questionnaire():
    return {
        "goal": "general_health",
        "meals_per_day": 3,
        "diet_pattern": "omnivore",
        "training_days_per_week": 3,
        "change_pace": "conservative",
        "allergies": [],
        "intolerances": [],
        "disliked_foods": [],
        "preferred_foods": [],
        "available_ingredients": [],
        "custom_targets": {},
        "budget": "moderate",
        "prep_minutes": 30,
        "notes": "",
    }


def generated_diet(targets):
    per_meal = {
        "calories": round(targets["targetCalories"] / 3, 1),
        "protein": round(targets["targetProtein"] / 3, 1),
        "carbs": round(targets["targetCarbs"] / 3, 1),
        "fat": round(targets["targetFat"] / 3, 1),
    }
    return {
        "type": "diet_plan",
        "title": "Dieta do aluno",
        "description": "Três dias.",
        "days": [{"meals": [{
            "meal_type": name,
            "items": ["Arroz", "Feijão", "Ovos", "Vegetais"],
            "prep": "Prepare e sirva.",
            "prep_minutes": 20,
            "substitutions": [],
            **per_meal,
        } for name in ("Café", "Almoço", "Jantar")]} for _ in range(3)],
    }


def test_only_admin_can_enable_professional(app, client):
    register(client, "normal")
    with app.app_context():
        target = User(username="target")
        target.set_password("strong-password")
        db.session.add(target)
        db.session.commit()
        target_id = target.id

    assert client.patch(
        f"/api/admin/users/{target_id}/professional", json={"is_professional": True}
    ).status_code == 403

    admin_client = app.test_client()
    register(admin_client, "admin")
    with app.app_context():
        User.query.filter_by(username="admin").one().is_admin = True
        db.session.commit()
    response = admin_client.patch(
        f"/api/admin/users/{target_id}/professional",
        json={
            "is_professional": True,
            "professional_scope": "both",
            "duration_days": 90,
        },
    )
    assert response.status_code == 200
    assert response.get_json()["user"]["is_professional"] is True
    assert response.get_json()["user"]["professional_entitled"] is True
    with app.app_context():
        grant = Subscription.query.filter_by(user_id=target_id, provider="admin").one()
        assert grant.plan_code == "professional_complete"
        assert 89 <= (grant.current_period_end - datetime.utcnow()).days <= 90


def test_admin_professional_grant_expires_without_affecting_approval(app):
    admin_client = app.test_client()
    register(admin_client, "grant-admin")
    with app.app_context():
        admin = User.query.filter_by(username="grant-admin").one()
        admin.is_admin = True
        target = User(username="temporary-professional")
        target.set_password("strong-password")
        db.session.add(target)
        db.session.commit()
        target_id = target.id

    granted = admin_client.patch(
        f"/api/admin/users/{target_id}/professional",
        json={
            "is_professional": True,
            "professional_scope": "workout",
            "duration_days": 7,
        },
    )
    assert granted.status_code == 200

    with app.app_context():
        grant = Subscription.query.filter_by(user_id=target_id, provider="admin").one()
        grant.current_period_end = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
        target = db.session.get(User, target_id)
        assert target.is_professional is True
        assert target.has_entitlement("professional") is False


def test_professional_grant_takes_priority_then_paid_premium_resumes(app):
    now = datetime.utcnow()
    with app.app_context():
        user = User(
            username="overlapping-grants",
            is_professional=True,
            professional_scope="both",
        )
        db.session.add(user)
        db.session.flush()
        paid = Subscription(
            user=user,
            provider="asaas",
            external_subscription_id="paid-premium-overlap",
            status="active",
            plan_code="premium_student",
            current_period_end=now + timedelta(days=30),
        )
        grant = Subscription(
            user=user,
            provider="admin",
            external_subscription_id="admin-professional-overlap",
            status="active",
            plan_code="professional_complete",
            current_period_end=now + timedelta(days=7),
        )
        db.session.add_all((paid, grant))
        db.session.commit()

        assert user.effective_plan_code() == "professional_complete"
        assert user.has_entitlement("professional") is True

        grant.current_period_end = now - timedelta(seconds=1)
        db.session.commit()
        assert user.effective_plan_code() == "premium_student"
        assert user.has_entitlement("premium") is True
        assert user.has_entitlement("professional") is False


def test_admin_revoking_professional_releases_students(app):
    trainer_client = app.test_client()
    student_client = app.test_client()
    student_id = link_student(app, trainer_client, student_client)
    admin_client = app.test_client()
    register(admin_client, "admin")
    with app.app_context():
        admin = User.query.filter_by(username="admin").one()
        admin.is_admin = True
        trainer_id = User.query.filter_by(username="trainer").one().id
        db.session.commit()

    response = admin_client.patch(
        f"/api/admin/users/{trainer_id}/professional",
        json={"is_professional": False},
    )
    assert response.status_code == 200
    assert trainer_client.get(f"/api/professional/students/{student_id}").status_code == 403
    with app.app_context():
        assert ProfessionalStudentRelationship.query.filter_by(status="active").count() == 0


def test_professional_scope_limits_plan_type(app):
    trainer_client = app.test_client()
    register(trainer_client, "scoped-trainer")
    enable_professional(app, "scoped-trainer")
    with app.app_context():
        trainer = User.query.filter_by(username="scoped-trainer").one()
        trainer.professional_scope = "workout"
        db.session.commit()

    missing_student_id = uuid4()
    assert trainer_client.get(
        f"/api/professional/students/{missing_student_id}/diet-plans"
    ).status_code == 403
    assert trainer_client.get(
        f"/api/professional/students/{missing_student_id}/workout-plans"
    ).status_code == 404


def test_active_professional_subscription_drives_entitlements(app):
    with app.app_context():
        trainer = User(
            username="subscribed-trainer",
            is_professional=True,
            professional_scope="workout",
        )
        db.session.add(trainer)
        db.session.flush()
        db.session.add(Subscription(
            user_id=trainer.id,
            provider="asaas",
            external_subscription_id="sub_professional_scope",
            status="active",
            plan_code="professional_single",
            current_period_end=datetime.utcnow() + timedelta(days=30),
        ))
        db.session.commit()

        assert trainer.has_entitlement("premium") is True
        assert trainer.has_entitlement("professional") is True
        assert trainer.has_entitlement("workout") is True
        assert trainer.has_entitlement("diet") is False
        serialized = trainer.to_dict()
        assert serialized["professional_entitled"] is True
        assert serialized["professional_scope"] == "workout"

        trainer.professional_scope = None
        assert trainer.has_entitlement("professional") is True
        assert trainer.has_entitlement("workout") is False
        assert trainer.has_entitlement("diet") is False


def test_professional_plan_limits_student_slots(app):
    trainer_client = app.test_client()
    register(trainer_client, "limited-trainer")
    enable_professional(app, "limited-trainer")

    for _ in range(5):
        assert trainer_client.post("/api/professional/invitations", json={}).status_code == 201
    response = trainer_client.post("/api/professional/invitations", json={})
    assert response.status_code == 409
    assert "5 alunos" in response.get_json()["error"]


def test_invitation_requires_and_records_data_sharing_consent(app):
    trainer_client = app.test_client()
    student_client = app.test_client()
    register(trainer_client, "sharing-trainer")
    enable_professional(app, "sharing-trainer")
    token = trainer_client.post("/api/professional/invitations", json={}).get_json()["token"]
    register(student_client, "sharing-student")

    missing = student_client.post(f"/api/invitations/{token}/accept", json={})
    assert missing.status_code == 400
    assert missing.get_json()["code"] == "data_sharing_consent_required"
    assert student_client.post(
        f"/api/invitations/{token}/accept", json=SHARING_CONSENT
    ).status_code == 200
    with app.app_context():
        relationship = ProfessionalStudentRelationship.query.filter_by(status="active").one()
        assert relationship.data_sharing_consent_version == PROFESSIONAL_SHARING_VERSION
        assert relationship.data_sharing_consented_at is not None


def test_admin_revoking_professional_invalidates_pending_invites(app):
    trainer_client = app.test_client()
    register(trainer_client, "trainer")
    enable_professional(app, "trainer")
    token = trainer_client.post("/api/professional/invitations", json={}).get_json()["token"]
    admin_client = app.test_client()
    student_client = app.test_client()
    register(admin_client, "admin")
    register(student_client, "student")
    with app.app_context():
        admin = User.query.filter_by(username="admin").one()
        admin.is_admin = True
        trainer_id = User.query.filter_by(username="trainer").one().id
        db.session.commit()

    assert admin_client.patch(
        f"/api/admin/users/{trainer_id}/professional",
        json={"is_professional": False},
    ).status_code == 200
    assert student_client.post(f"/api/invitations/{token}/accept", json=SHARING_CONSENT).status_code == 404


def test_invitation_links_existing_account_and_only_one_professional(app):
    trainer_client = app.test_client()
    student_client = app.test_client()
    student_id = link_student(app, trainer_client, student_client)

    students = trainer_client.get("/api/professional/students").get_json()["items"]
    assert students[0]["id"] == str(student_id)

    second_client = app.test_client()
    register(second_client, "second-trainer")
    enable_professional(app, "second-trainer")
    token = second_client.post("/api/professional/invitations", json={}).get_json()["token"]
    assert student_client.post(f"/api/invitations/{token}/accept", json=SHARING_CONSENT).status_code == 409
    with app.app_context():
        assert ProfessionalStudentRelationship.query.filter_by(status="active").count() == 1


def test_invitation_stores_only_token_hash(app):
    trainer_client = app.test_client()
    register(trainer_client, "trainer")
    enable_professional(app, "trainer")
    token = trainer_client.post("/api/professional/invitations", json={}).get_json()["token"]

    with app.app_context():
        relationship = ProfessionalStudentRelationship.query.one()
        assert relationship.invite_token_hash != token
        assert len(relationship.invite_token_hash) == 64


def test_offline_student_can_have_profile_and_manual_plan_then_link_account(app):
    trainer_client = app.test_client()
    student_client = app.test_client()
    register(trainer_client, "roster-trainer")
    enable_professional(app, "roster-trainer")

    created = trainer_client.post("/api/professional/students", json={
        "name": "Aluno sem conta",
        "profile": {
            "age": 29,
            "gender": "masculino",
            "goal": "strength",
            "activity_level": "moderado",
            "weight": 78,
            "height": 179,
        },
    })
    assert created.status_code == 201
    student = created.get_json()["student"]
    student_id = student["id"]
    assert student_id.startswith("offline-")
    assert student["is_offline"] is True
    assert student["profile"]["age"] == 29

    plan_response = trainer_client.post(
        f"/api/professional/students/{student_id}/workout-plans",
        json={
            "questionnaire": workout_questionnaire(),
            "plan": {
                "type": "workout_plan",
                "title": "Treino preparado offline",
                "days": [
                    {"title": "A", "exercises": [{"catalog_key": "agachamento_goblet", "sets": 3, "reps": "8-12", "rest_seconds": 60}]},
                    {"title": "B", "exercises": [{"catalog_key": "supino_reto_halteres", "sets": 3, "reps": "8-12", "rest_seconds": 60}]},
                ],
            },
        },
    )
    assert plan_response.status_code == 201
    plan_id = plan_response.get_json()["plan"]["id"]
    assert trainer_client.get(
        f"/api/professional/students/{student_id}/workout-plans/{plan_id}"
    ).status_code == 200
    with app.app_context():
        plan = db.session.get(WorkoutPlan, plan_id)
        relationship = db.session.get(ProfessionalStudentRelationship, int(student_id.split("-")[1]))
        assert plan.user_id is None
        assert plan.professional_student_relationship_id == relationship.id
        assert relationship.status == "offline"

    invitation = trainer_client.post(f"/api/professional/students/{student_id}/invitation", json={})
    assert invitation.status_code == 201
    register(student_client, "roster-account")
    accepted = student_client.post(
        f"/api/invitations/{invitation.get_json()['token']}/accept",
        json=SHARING_CONSENT,
    )
    assert accepted.status_code == 200
    assert trainer_client.get(
        f"/api/professional/students/{accepted.get_json()['relationship']['student']['id']}/workout-plans"
    ).get_json()[0]["id"] == plan_id
    with app.app_context():
        actual_user = User.query.filter_by(username="roster-account").one()
        relationship = db.session.get(ProfessionalStudentRelationship, int(student_id.split("-")[1]))
        plan = db.session.get(WorkoutPlan, plan_id)
        assert relationship.status == "active"
        assert relationship.student_user_id == actual_user.id
        assert plan.user_id == actual_user.id
        assert plan.professional_student_relationship_id is None
        assert actual_user.profile.age == 29
        assert actual_user.profile.height == 179


def test_profile_age_advances_by_calendar_year(app):
    client = app.test_client()
    register(client, "age-user")
    with app.app_context():
        user = User.query.filter_by(username="age-user").one()
        profile = UserProfile(user_id=user.id, age=30)
        db.session.add(profile)
        db.session.flush()
        birth_year = profile.birth_year
        profile.birth_year = birth_year - 1
        assert profile.age == 31


def test_non_professional_cannot_create_invitation(client):
    register(client, "normal")
    assert client.post("/api/professional/invitations", json={}).status_code == 403


def test_professional_ai_uses_student_and_draft_is_hidden(app, monkeypatch):
    trainer_client = app.test_client()
    student_client = app.test_client()
    student_id = link_student(app, trainer_client, student_client)
    with app.app_context():
        trainer = User.query.filter_by(username="trainer").one()
        trainer.is_premium = True
        db.session.add(UserProfile(
            user_id=student_id,
            age=30,
            gender="masculino",
            activity_level="moderado",
            weight=80,
            height=180,
        ))
        db.session.commit()

    captured = {}

    def generate(*args):
        captured["profile_user_id"] = args[1].user_id
        return generated_workout()

    monkeypatch.setattr("src.routes.professional_routes.generate_workout_plan", generate)
    created = trainer_client.post(
        f"/api/professional/students/{student_id}/workout-plans/generate",
        json=workout_questionnaire(),
    )
    assert created.status_code == 201
    plan = created.get_json()["plan"]
    assert plan["status"] == "draft"
    assert plan["source"] == "ai"
    assert captured["profile_user_id"] == student_id
    assert student_client.get("/api/workout_plans").get_json() == []

    published = trainer_client.post(
        f"/api/professional/students/{student_id}/workout-plans/{plan['id']}/publish",
        json={},
    )
    assert published.status_code == 200
    assert student_client.get("/api/workout_plans").get_json()[0]["author_username"] == "trainer"
    with app.app_context():
        assert DelegatedActionAudit.query.filter_by(action="workout_plan.published").count() == 1


def test_async_professional_workout_keeps_student_as_plan_owner(app, monkeypatch):
    trainer_client = app.test_client()
    student_client = app.test_client()
    student_id = link_student(app, trainer_client, student_client)
    with app.app_context():
        trainer = User.query.filter_by(username="trainer").one()
        trainer_id = trainer.id
        db.session.add(UserProfile(
            user_id=student_id,
            age=31,
            gender="masculino",
            activity_level="moderado",
            weight=81,
            height=181,
        ))
        db.session.commit()

    app.config["AI_ASYNC_ENABLED"] = True
    monkeypatch.setattr(execute_ai_job, "apply_async", lambda **_kwargs: None)
    captured = {}

    def generate(*args):
        captured["profile_user_id"] = args[1].user_id
        return generated_workout()

    monkeypatch.setattr("src.routes.professional_routes.generate_workout_plan", generate)
    queued = trainer_client.post(
        f"/api/professional/students/{student_id}/workout-plans/generate",
        json=workout_questionnaire(),
    )

    assert queued.status_code == 202
    task_id = queued.get_json()["job_id"]
    with app.app_context():
        task = db.session.get(AITask, task_id)
        assert task.user_id == trainer_id
        assert task.route_params["student_id"] == str(student_id)

    execute_ai_job.run(task_id)

    with app.app_context():
        task = db.session.get(AITask, task_id)
        plan = WorkoutPlan.query.filter_by(ai_task_id=task.id).one()
        assert task.status == "succeeded"
        assert captured["profile_user_id"] == student_id
        assert plan.user_id == student_id
        assert plan.author_user_id == trainer_id


def test_async_professional_job_rechecks_specialty_scope(app, monkeypatch):
    trainer_client = app.test_client()
    student_client = app.test_client()
    student_id = link_student(app, trainer_client, student_client)
    app.config["AI_ASYNC_ENABLED"] = True
    monkeypatch.setattr(execute_ai_job, "apply_async", lambda **_kwargs: None)
    queued = trainer_client.post(
        f"/api/professional/students/{student_id}/workout-plans/generate",
        json=workout_questionnaire(),
    )
    task_id = queued.get_json()["job_id"]
    with app.app_context():
        User.query.filter_by(username="trainer").one().professional_scope = "diet"
        db.session.commit()

    execute_ai_job.run(task_id)

    with app.app_context():
        task = db.session.get(AITask, task_id)
        assert task.status == "failed"
        assert task.http_status == 403
        assert WorkoutPlan.query.count() == 0


def test_approved_professional_without_subscription_cannot_use_workspace(app):
    trainer_client = app.test_client()
    register(trainer_client, "approved-only")
    with app.app_context():
        trainer = User.query.filter_by(username="approved-only").one()
        trainer.is_professional = True
        trainer.professional_scope = "workout"
        db.session.commit()

    assert trainer_client.post(
        "/api/professional/invitations", json={}
    ).status_code == 403


def test_professional_errors_are_json(app):
    trainer_client = app.test_client()
    student_client = app.test_client()
    link_student(app, trainer_client, student_client)

    response = trainer_client.get(f"/api/professional/students/{uuid4()}")

    assert response.status_code == 404
    assert response.is_json
    assert response.get_json() == {"error": "Aluno não encontrado."}


def test_diet_generation_and_suggestion_stay_in_draft(app, monkeypatch):
    trainer_client = app.test_client()
    student_client = app.test_client()
    student_id = link_student(app, trainer_client, student_client)
    with app.app_context():
        trainer = User.query.filter_by(username="trainer").one()
        trainer.is_premium = True
        db.session.add(UserProfile(
            user_id=student_id,
            age=30,
            gender="masculino",
            activity_level="moderado",
            weight=80,
            height=180,
        ))
        db.session.commit()

    monkeypatch.setattr(
        "src.routes.professional_routes.generate_diet_plan",
        lambda questionnaire, profile, targets, correction: generated_diet(targets),
    )
    created = trainer_client.post(
        f"/api/professional/students/{student_id}/diet-plans/generate",
        json=diet_questionnaire(),
    )
    assert created.status_code == 201
    plan = created.get_json()["plan"]
    assert student_client.get("/api/diet_plans").get_json() == []

    monkeypatch.setattr(
        "src.routes.professional_routes.generate_diet_day",
        lambda questionnaire, profile, existing, feedback, targets, correction: {
            "type": "diet_plan_day",
            "meals": generated_diet(targets)["days"][0]["meals"],
        },
    )
    suggestion = trainer_client.post(
        f"/api/professional/students/{student_id}/diet-plans/{plan['id']}/suggest",
        json={"day": 1, "feedback": "trocar o café"},
    )
    assert suggestion.status_code == 200
    applied = trainer_client.put(
        f"/api/professional/students/{student_id}/diet-plans/{plan['id']}/days/1",
        json={"meals": suggestion.get_json()["meals"]},
    )
    assert applied.status_code == 200
    with app.app_context():
        assert db.session.get(DietPlan, plan["id"]).status == "draft"


def test_professional_diet_generation_reports_incomplete_student_profile(app, monkeypatch):
    trainer_client = app.test_client()
    student_client = app.test_client()
    student_id = link_student(app, trainer_client, student_client)
    called = {"value": False}
    monkeypatch.setattr(
        "src.routes.professional_routes.generate_diet_plan",
        lambda *args: called.update(value=True),
    )

    response = trainer_client.post(
        f"/api/professional/students/{student_id}/diet-plans/generate",
        json=diet_questionnaire(),
    )

    assert response.status_code == 400
    assert "profile.age" in response.get_json()["fields"]
    assert called["value"] is False


def test_professional_workout_generation_reports_missing_preferences(app, monkeypatch):
    trainer_client = app.test_client()
    student_client = app.test_client()
    student_id = link_student(app, trainer_client, student_client)
    called = {"value": False}
    monkeypatch.setattr(
        "src.routes.professional_routes.generate_workout_plan",
        lambda *args: called.update(value=True),
    )

    response = trainer_client.post(
        f"/api/professional/students/{student_id}/workout-plans/generate",
        json={},
    )

    assert response.status_code == 400
    assert {
        "goal",
        "experience_level",
        "days_per_week",
        "session_duration",
        "equipment",
    } <= response.get_json()["fields"].keys()
    assert called["value"] is False


def test_revoked_relationship_blocks_access_but_keeps_published_plan(app, monkeypatch):
    trainer_client = app.test_client()
    student_client = app.test_client()
    student_id = link_student(app, trainer_client, student_client)
    with app.app_context():
        User.query.filter_by(username="trainer").one().is_premium = True
        db.session.commit()
    monkeypatch.setattr("src.routes.professional_routes.generate_workout_plan", lambda *args: generated_workout())
    plan = trainer_client.post(
        f"/api/professional/students/{student_id}/workout-plans/generate",
        json=workout_questionnaire(),
    ).get_json()["plan"]
    assert trainer_client.post(
        f"/api/professional/students/{student_id}/workout-plans/{plan['id']}/publish", json={}
    ).status_code == 200

    assert trainer_client.delete(f"/api/professional/students/{student_id}").status_code == 200
    assert trainer_client.get(f"/api/professional/students/{student_id}").status_code == 404
    assert student_client.get("/api/workout_plans").get_json()[0]["id"] == plan["id"]
    with app.app_context():
        assert db.session.get(WorkoutPlan, plan["id"]).status == "published"


def test_student_can_revoke_own_relationship(app):
    trainer_client = app.test_client()
    student_client = app.test_client()
    student_id = link_student(app, trainer_client, student_client)

    current = student_client.get("/api/professional-relationship")
    assert current.status_code == 200
    assert current.get_json()["relationship"]["professional"]["username"] == "trainer"
    assert student_client.delete("/api/professional-relationship").status_code == 200
    assert trainer_client.get(f"/api/professional/students/{student_id}").status_code == 404
    assert student_client.get("/api/professional-relationship").get_json()["relationship"] is None
