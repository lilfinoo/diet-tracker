from datetime import datetime, timedelta, timezone

import pytest

from src.models.user import Subscription, User, db
from src.services.revenuecat import RevenueCatError
from tests.helpers import registration_payload


def setup_user(app, client):
    client.post('/api/register', json=registration_payload('rc-user'))
    client.post('/api/login', json={'username': 'rc-user', 'password': 'strong-password'})
    app.config.update(REVENUECAT_SECRET_API_KEY='secret-test', REVENUECAT_IOS_API_KEY='appl_public',
                      REVENUECAT_WEBHOOK_AUTHORIZATION='Bearer webhook-secret')
    with app.app_context():
        return str(User.query.filter_by(username='rc-user').one().id)


def subscriber(*, expired=False, sandbox=False, trial=False, product='ai.fittracker.premium.monthly'):
    end = datetime.now(timezone.utc) + timedelta(days=-1 if expired else 7)
    return {'entitlements': {'fittracker_ai_pro': {'product_identifier': product,
            'expires_date': end.isoformat(), 'purchase_date': datetime.now(timezone.utc).isoformat()}},
            'subscriptions': {product: {'store': 'app_store', 'is_sandbox': sandbox,
                              'period_type': 'trial' if trial else 'normal'}}}


def test_sync_uses_session_uuid_and_never_client_entitlement(app, client, monkeypatch):
    user_id = setup_user(app, client)
    seen = []
    monkeypatch.setattr('src.services.revenuecat.fetch_subscriber',
                        lambda uid: seen.append(str(uid)) or subscriber(trial=True))
    result = client.post('/api/billing/revenuecat/sync', json={'app_user_id': 'other', 'is_premium': True})
    assert result.status_code == 200
    assert seen == [user_id]
    assert result.json['is_premium'] is True
    assert result.json['subscription']['status'] == 'trialing'
    client.post('/api/billing/revenuecat/sync')
    with app.app_context():
        assert Subscription.query.filter_by(provider='revenuecat').count() == 1


@pytest.mark.parametrize('state', [subscriber(expired=True), subscriber(sandbox=True), subscriber(product='fake')])
def test_unverified_or_expired_cannot_grant(app, client, monkeypatch, state):
    setup_user(app, client)
    monkeypatch.setattr('src.services.revenuecat.fetch_subscriber', lambda uid: state)
    assert client.post('/api/billing/revenuecat/sync').json['is_premium'] is False


def test_expiration_preserves_asaas_access(app, client, monkeypatch):
    user_id = setup_user(app, client)
    monkeypatch.setattr('src.services.revenuecat.fetch_subscriber', lambda uid: subscriber())
    client.post('/api/billing/revenuecat/sync')
    with app.app_context():
        user = User.query.filter_by(username='rc-user').one()
        db.session.add(Subscription(user_id=user.id, provider='asaas', external_subscription_id='asaas-existing',
                                   status='active', plan_code='premium_student',
                                   current_period_end=datetime.utcnow() + timedelta(days=20)))
        db.session.commit()
    monkeypatch.setattr('src.services.revenuecat.fetch_subscriber', lambda uid: subscriber(expired=True))
    result = client.post('/api/billing/revenuecat/sync')
    assert result.json['is_premium'] is True
    assert result.json['subscription']['provider'] == 'asaas'
    with app.app_context():
        assert Subscription.query.filter_by(provider='revenuecat', external_subscription_id=user_id).one().status == 'expired'


def test_webhook_auth_and_canonical_duplicate_state(app, client, monkeypatch):
    user_id = setup_user(app, client)
    seen = []
    monkeypatch.setattr('src.services.revenuecat.fetch_subscriber', lambda uid: seen.append(str(uid)) or subscriber())
    event = {'event': {'id': 'event-1', 'type': 'EXPIRATION', 'app_user_id': user_id}}
    assert client.post('/api/billing/revenuecat/webhook', json=event).status_code == 401
    assert not seen
    headers = {'Authorization': 'Bearer webhook-secret'}
    for _ in range(2):
        assert client.post('/api/billing/revenuecat/webhook', json=event, headers=headers).status_code == 200
    with app.app_context():
        assert Subscription.query.filter_by(provider='revenuecat').count() == 1
        assert User.query.filter_by(username='rc-user').one().has_entitlement('premium')


def test_provider_failure_does_not_erase_access(app, client, monkeypatch):
    setup_user(app, client)
    monkeypatch.setattr('src.services.revenuecat.fetch_subscriber', lambda uid: subscriber())
    client.post('/api/billing/revenuecat/sync')
    def unavailable(uid):
        raise RevenueCatError('Unavailable')
    monkeypatch.setattr('src.services.revenuecat.fetch_subscriber', unavailable)
    assert client.post('/api/billing/revenuecat/sync').status_code == 502
    with app.app_context():
        assert User.query.filter_by(username='rc-user').one().has_entitlement('premium')


def test_config_does_not_expose_secret_and_sync_requires_login(app, client):
    app.config.update(REVENUECAT_SECRET_API_KEY='private', REVENUECAT_IOS_API_KEY='appl_public')
    response = client.get('/api/billing/revenuecat/config')
    assert response.json['public_api_key'] == 'appl_public'
    assert 'private' not in response.text
    assert client.post('/api/billing/revenuecat/sync').status_code == 401


def test_transfer_refreshes_both_accounts_and_revokes_previous(app, client, monkeypatch):
    old_id = setup_user(app, client)
    with app.app_context():
        new_user = User(username='rc-transfer')
        new_user.set_password('strong-password')
        db.session.add(new_user)
        db.session.commit()
        new_id = str(new_user.id)
    monkeypatch.setattr('src.services.revenuecat.fetch_subscriber', lambda uid: subscriber())
    client.post('/api/billing/revenuecat/sync')
    monkeypatch.setattr('src.services.revenuecat.fetch_subscriber',
                        lambda uid: {} if str(uid) == old_id else subscriber())
    result = client.post('/api/billing/revenuecat/webhook',
                         headers={'Authorization': 'Bearer webhook-secret'},
                         json={'event': {'type': 'TRANSFER', 'transferred_from': [old_id],
                                         'transferred_to': [new_id]}})
    assert result.status_code == 200
    with app.app_context():
        assert not User.query.filter_by(username='rc-user').one().has_entitlement('premium')
        assert User.query.filter_by(username='rc-transfer').one().has_entitlement('premium')


def test_http_client_keeps_secret_on_server_and_rejects_failure(app, monkeypatch):
    from src.services.revenuecat import fetch_subscriber
    calls = []
    class Response:
        status_code = 200
        def json(self):
            return {'subscriber': subscriber()}
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()
    monkeypatch.setattr('src.services.revenuecat.requests.get', get)
    with app.app_context():
        with pytest.raises(RevenueCatError) as missing:
            fetch_subscriber('user')
        assert missing.value.status_code == 503
        app.config['REVENUECAT_SECRET_API_KEY'] = 'private-key'
        assert fetch_subscriber('user/id')['entitlements']
        assert calls[0][0].endswith('user%2Fid')
        assert calls[0][1]['headers']['Authorization'] == 'Bearer private-key'
        Response.status_code = 429
        with pytest.raises(RevenueCatError):
            fetch_subscriber('user')


def test_apple_subscription_does_not_block_account_deletion(app, client, monkeypatch):
    from src.routes.account_routes import _subscription_block
    setup_user(app, client)
    monkeypatch.setattr('src.services.revenuecat.fetch_subscriber', lambda uid: subscriber())
    client.post('/api/billing/revenuecat/sync')
    with app.app_context():
        assert _subscription_block(User.query.filter_by(username='rc-user').one()) is None


def test_csrf_protects_sync_but_not_authenticated_webhook(app, client, monkeypatch):
    user_id = setup_user(app, client)
    app.config['CSRF_PROTECTION'] = True
    monkeypatch.setattr('src.services.revenuecat.fetch_subscriber', lambda uid: subscriber())
    assert client.post('/api/billing/revenuecat/sync').status_code == 403
    assert client.post('/api/billing/revenuecat/webhook',
                       headers={'Authorization': 'Bearer webhook-secret'},
                       json={'event': {'app_user_id': user_id}}).status_code == 200


def test_sandbox_only_grants_allowlisted_user(app, client, monkeypatch):
    user_id = setup_user(app, client)
    monkeypatch.setattr('src.services.revenuecat.fetch_subscriber', lambda uid: subscriber(sandbox=True))
    app.config['REVENUECAT_SANDBOX_USER_IDS'] = 'another-user'
    assert client.post('/api/billing/revenuecat/sync').json['is_premium'] is False
    app.config['REVENUECAT_SANDBOX_USER_IDS'] = user_id
    assert client.post('/api/billing/revenuecat/sync').json['is_premium'] is True


def test_bad_expiry_rejects_sync_without_writing(app, client, monkeypatch):
    setup_user(app, client)
    state = subscriber()
    state['entitlements']['fittracker_ai_pro']['expires_date'] = 'invalid'
    monkeypatch.setattr('src.services.revenuecat.fetch_subscriber', lambda uid: state)
    assert client.post('/api/billing/revenuecat/sync').status_code == 502
    with app.app_context():
        assert Subscription.query.filter_by(provider='revenuecat').count() == 0


def test_webhook_limits_canonical_lookups(app, client, monkeypatch):
    from uuid import uuid4
    setup_user(app, client)
    seen = []
    monkeypatch.setattr('src.services.revenuecat.fetch_subscriber', lambda uid: seen.append(uid) or {})
    response = client.post('/api/billing/revenuecat/webhook',
                           headers={'Authorization': 'Bearer webhook-secret'},
                           json={'event': {'aliases': [str(uuid4()) for _ in range(21)]}})
    assert response.status_code == 400
    assert seen == []


def test_unicode_webhook_header_fails_without_server_error(app, client):
    setup_user(app, client)
    response = client.post('/api/billing/revenuecat/webhook',
                           headers={'Authorization': 'Bearer inválido'}, json={'event': {}})
    assert response.status_code == 401
