from uuid import uuid4

from src.models.user import (
    DelegatedActionAudit,
    DietPlan,
    ProfessionalStudentRelationship,
    User,
    UserProfile,
    WorkoutPlan,
    db,
)


def register(client, username):
    return client.post("/api/register", json={"username": username, "password": "strong-password"})


def enable_professional(app, username, premium=False):
    with app.app_context():
        user = User.query.filter_by(username=username).one()
        user.is_professional = True
        user.is_premium = premium
        db.session.commit()


def link_student(app, professional_client, student_client, professional_name="trainer", student_name="student"):
    register(professional_client, professional_name)
    enable_professional(app, professional_name)
    invitation = professional_client.post("/api/professional/invitations", json={}).get_json()
    register(student_client, student_name)
    accepted = student_client.post(f"/api/invitations/{invitation['token']}/accept", json={})
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
        ["agachamento_goblet", "supino_reto_halteres", "remada_unilateral_halter", "bird_dog"],
    ]
    return {
        "type": "workout_plan",
        "title": "Treino do aluno",
        "description": "Plano revisável.",
        "days": [{
            "focus": "Corpo inteiro",
            "exercises": [{
                "catalog_key": key,
                "sets": 3,
                "reps": "8-12",
                "weight": "Moderada",
                "rest_seconds": 60,
                "effort_guidance": "2 repetições em reserva",
                "notes": "Execução controlada",
            } for key in keys],
        } for keys in day_keys],
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
        f"/api/admin/users/{target_id}/professional", json={"is_professional": True}
    )
    assert response.status_code == 200
    assert response.get_json()["user"]["is_professional"] is True


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
    assert student_client.post(f"/api/invitations/{token}/accept", json={}).status_code == 404


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
    assert student_client.post(f"/api/invitations/{token}/accept", json={}).status_code == 409
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

    def generate(questionnaire, profile):
        captured["profile_user_id"] = profile.user_id
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


def test_free_professional_can_create_manual_but_not_generate(app):
    trainer_client = app.test_client()
    student_client = app.test_client()
    student_id = link_student(app, trainer_client, student_client)

    assert trainer_client.post(
        f"/api/professional/students/{student_id}/workout-plans/generate",
        json=workout_questionnaire(),
    ).status_code == 403

    manual = generated_workout()
    manual["days"] = [{
        "code": chr(65 + index),
        "title": f"Treino {chr(65 + index)}",
        **day,
    } for index, day in enumerate(manual["days"])]
    response = trainer_client.post(
        f"/api/professional/students/{student_id}/workout-plans",
        json={"questionnaire": workout_questionnaire(), "plan": manual},
    )
    assert response.status_code == 201
    assert response.get_json()["plan"]["source"] == "manual"


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
