from datetime import datetime, timedelta
from uuid import uuid4

from src.legal import PROFESSIONAL_SHARING_VERSION
from src.models.user import Subscription, User, WorkoutPlan, db
from tests.helpers import registration_payload
from tests.test_guided_plans import workout_questionnaire


def account(app, name, *, professional=False, admin=False):
    client = app.test_client()
    assert client.post('/api/register', json=registration_payload(name)).status_code == 201
    with app.app_context():
        user = User.query.filter_by(username=name).one()
        user.is_admin = admin
        user.is_professional = professional
        user.professional_scope = 'workout' if professional else None
        if professional:
            db.session.add(Subscription(user_id=user.id, provider='admin',
                plan_code='professional_single', status='active',
                current_period_end=datetime.utcnow() + timedelta(days=30)))
        user_id = str(user.id)
        db.session.commit()
    return client, user_id


def roster(client):
    response = client.post('/api/professional/students', json={
        'name': 'Aluno teste', 'profile': {'age': 30, 'weight': 75, 'height': 175},
    })
    assert response.status_code == 201, response.json
    return response.json['student']['id']


def workout():
    return {'questionnaire': workout_questionnaire(), 'plan': {
        'type': 'workout_plan', 'title': 'Treino manual', 'description': 'Plano do personal',
        'days': [{'exercises': [{'catalog_key': 'supino_maquina', 'sets': 3,
                  'reps': '8-12', 'rest_seconds': 60}]} for _ in range(2)],
    }}


def test_personal_gate_requires_approval_and_active_grant(app):
    client, uid = account(app, 'regular')
    assert client.get('/api/professional/students').status_code == 403
    with app.app_context():
        user = db.session.get(User, uid)
        user.is_professional = True
        user.professional_scope = 'workout'
        db.session.commit()
    assert client.get('/api/professional/students').status_code == 403


def test_offline_workout_crud_ownership_and_invitation_acceptance(app):
    coach, _ = account(app, 'coach', professional=True)
    other, _ = account(app, 'other', professional=True)
    student, uid = account(app, 'student')
    sid = roster(coach)
    path = f'/api/professional/students/{sid}/workout-plans'
    response = coach.post(path, json=workout())
    assert response.status_code == 201, response.json
    pid = response.json['plan']['id']
    assert other.get(path).status_code == 404
    assert other.get(f'{path}/{pid}').status_code == 404
    assert coach.put(f'{path}/{pid}', json=workout()).status_code == 200
    assert coach.post(f'{path}/{pid}/publish').status_code == 409
    invitation = coach.post(f'/api/professional/students/{sid}/invitation').json
    token = invitation['token']
    assert student.post(f'/api/invitations/{token}/accept', json={}).status_code == 400
    accepted = student.post(f'/api/invitations/{token}/accept', json={
        'data_sharing_consent': True,
        'data_sharing_consent_version': PROFESSIONAL_SHARING_VERSION,
    })
    assert accepted.status_code == 200, accepted.json
    path = f'/api/professional/students/{uid}/workout-plans'
    assert coach.get(f'{path}/{pid}').status_code == 200
    assert coach.post(f'{path}/{pid}/publish').status_code == 200
    assert coach.put(f'{path}/{pid}', json=workout()).status_code == 409
    with app.app_context():
        plan = db.session.get(WorkoutPlan, pid)
        assert str(plan.user_id) == uid
        assert plan.status == 'published'
    assert student.delete('/api/professional-relationship').status_code == 200
    assert coach.get(path).status_code == 404


def test_roster_limit_invalid_id_and_expired_invitation_preserve_student(app):
    coach, _ = account(app, 'coach-limit', professional=True)
    sid = roster(coach)
    for _ in range(4):
        roster(coach)
    assert coach.post('/api/professional/students', json={}).status_code == 409
    assert coach.get('/api/professional/students/not-a-uuid').status_code == 404
    assert coach.get(f'/api/professional/students/{uuid4()}').status_code == 404
    assert coach.post(f'/api/professional/students/{sid}/invitation').status_code == 201
    assert coach.delete('/api/professional/invitations/1').status_code == 200
    assert len(coach.get('/api/professional/students').json['items']) == 5


def test_admin_professional_grant_and_revoke(app):
    admin, _ = account(app, 'admin-grant', admin=True)
    coach, uid = account(app, 'grant-target')
    url = f'/api/admin/users/{uid}/professional'
    assert coach.patch(url, json={'is_professional': True, 'duration_days': 30}).status_code == 403
    response = admin.patch(url, json={'is_professional': True, 'duration_days': 30})
    assert response.status_code == 200, response.json
    assert coach.get('/api/professional/students').status_code == 200
    assert admin.patch(url, json={'is_professional': False}).status_code == 200
    assert coach.get('/api/professional/students').status_code == 403


def test_expired_offline_invitation_preserves_roster(app):
    from src.models.user import ProfessionalStudentRelationship
    coach, _ = account(app, 'coach-expiry', professional=True)
    sid = roster(coach)
    invitation = coach.post(f'/api/professional/students/{sid}/invitation').json
    with app.app_context():
        relationship = db.session.get(ProfessionalStudentRelationship, invitation['invitation']['id'])
        relationship.invite_expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
    assert coach.get('/api/professional/invitations').json == []
    assert coach.get(f'/api/professional/students/{sid}').status_code == 200


def test_ai_generation_requires_both_consents_and_handles_failure(app, monkeypatch):
    from src.legal import AI_CONSENT_VERSION
    from src.models.user import ProfessionalStudentRelationship
    from src.services.ai import AIServiceError
    coach, coach_id = account(app, 'coach-ai', professional=True)
    _, student_id = account(app, 'student-ai')
    with app.app_context():
        db.session.add(ProfessionalStudentRelationship(
            professional_user_id=coach_id, student_user_id=student_id, status='active',
            invite_expires_at=datetime.utcnow() + timedelta(days=7),
            data_sharing_consent_version=PROFESSIONAL_SHARING_VERSION,
            data_sharing_consented_at=datetime.utcnow(),
        ))
        student = db.session.get(User, student_id)
        student.ai_consent_at = None
        student.ai_consent_version = None
        db.session.commit()
    url = f'/api/professional/students/{student_id}/workout-plans/generate'
    assert coach.post(url, json=workout_questionnaire()).status_code == 403
    with app.app_context():
        student = db.session.get(User, student_id)
        student.ai_consent_at = datetime.utcnow()
        student.ai_consent_version = AI_CONSENT_VERSION
        coach_user = db.session.get(User, coach_id)
        coach_user.ai_consent_at = datetime.utcnow()
        coach_user.ai_consent_version = AI_CONSENT_VERSION
        db.session.commit()
    def fail(*args, **kwargs):
        raise AIServiceError('test provider failure')
    monkeypatch.setattr('src.routes.professional_routes.generate_workout_plan', fail)
    response = coach.post(url, json=workout_questionnaire())
    assert response.status_code == 503
    assert 'test provider failure' not in response.get_data(as_text=True)
    with app.app_context():
        assert WorkoutPlan.query.filter_by(user_id=student_id).count() == 0
