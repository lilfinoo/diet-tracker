from collections import defaultdict
from datetime import datetime, timedelta
import csv
import io

from flask import Blueprint, abort, current_app, g, jsonify, request, send_file
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from src.models.user import (
    ChatMessage,
    DietEntry,
    DietPlan,
    ExerciseMediaReview,
    Measurement,
    ProfessionalApplication,
    ProfessionalStudentRelationship,
    Subscription,
    User,
    UserProfile,
    WorkoutPlan,
    WorkoutSession,
    db,
)
from src.routes.common import admin_required, json_body, page_query
from src.services.workout_plans import catalog_by_key
from src.services.workoutx import REVIEW_QUEUE, REVIEW_SEARCH_QUERIES, WorkoutXServiceError, approved_media, get_cached_gif, get_exercise, search_exercises


admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin/dashboard", methods=["GET"])
@admin_required
def admin_dashboard():
    stats = {
        "total_users": User.query.count(),
        "total_admins": User.query.filter_by(is_admin=True).count(),
        "total_banned": User.query.filter_by(is_banned=True).count(),
        "total_diet_entries": DietEntry.query.count(),
        "total_measurements": Measurement.query.count(),
        "total_chat_messages": ChatMessage.query.count(),
    }
    return jsonify(stats), 200


@admin_bp.route("/admin/users", methods=["GET"])
@admin_required
def list_users():
    users, _, _ = page_query(User.query.order_by(User.created_at.desc()))
    users = users.all()
    user_ids = [user.id for user in users]
    if not user_ids:
        return jsonify([]), 200

    def grouped_counts(model):
        return dict(db.session.query(model.user_id, func.count(model.id)).filter(model.user_id.in_(user_ids)).group_by(model.user_id))

    counts = {
        "diet_entries": grouped_counts(DietEntry),
        "measurements": grouped_counts(Measurement),
        "chat_messages": grouped_counts(ChatMessage),
        "workout_plans": grouped_counts(WorkoutPlan),
        "diet_plans": grouped_counts(DietPlan),
        "profiles": set(value for value, in db.session.query(UserProfile.user_id).filter(UserProfile.user_id.in_(user_ids))),
    }
    return jsonify([
        user.to_dict({
            "diet_entries": counts["diet_entries"].get(user.id, 0),
            "measurements": counts["measurements"].get(user.id, 0),
            "chat_messages": counts["chat_messages"].get(user.id, 0),
            "workout_plans": counts["workout_plans"].get(user.id, 0),
            "diet_plans": counts["diet_plans"].get(user.id, 0),
            "has_profile": user.id in counts["profiles"],
        }) for user in users
    ]), 200


@admin_bp.route("/admin/exercise-media/review", methods=["GET"])
@admin_required
def exercise_media_review_queue():
    catalog = catalog_by_key()
    reviews = {item.catalog_key: item for item in ExerciseMediaReview.query.all()}
    items = []
    for key in REVIEW_QUEUE:
        if approved_media(key):
            continue
        exercise = catalog.get(key)
        if not exercise:
            continue
        review = reviews.get(key)
        items.append({
            "catalog_key": key,
            "name": exercise["name"],
            "equipment": exercise["equipment"],
            "movement_pattern": exercise["movement_pattern"],
            "primary_muscle": exercise["primary_muscle"],
            "search_query": REVIEW_SEARCH_QUERIES[key],
            "review": {
                "provider_id": review.provider_id,
                "provider_name": review.provider_name,
                "provider_equipment": review.provider_equipment,
                "status": review.status,
            } if review else None,
        })
    return jsonify({"items": items}), 200


@admin_bp.route("/admin/exercise-media/search", methods=["GET"])
@admin_required
def search_exercise_media():
    query = str(request.args.get("query", "")).strip()
    if not 2 <= len(query) <= 80:
        return jsonify({"error": "Informe uma busca entre 2 e 80 caracteres."}), 400
    try:
        return jsonify({"items": search_exercises(query)}), 200
    except WorkoutXServiceError as error:
        current_app.logger.warning("WorkoutX review search failed: %s", error)
        return jsonify({"error": "Não foi possível buscar candidatos agora."}), 503


@admin_bp.route("/admin/exercise-media/candidates/<provider_id>", methods=["GET"])
@admin_required
def exercise_media_candidate(provider_id):
    try:
        gif_path = get_cached_gif(f"review-{provider_id}", provider_id)
    except WorkoutXServiceError:
        abort(404)
    return send_file(gif_path, mimetype="image/gif", conditional=True, max_age=86_400)


@admin_bp.route("/admin/exercise-media/<catalog_key>", methods=["PUT"])
@admin_required
def approve_exercise_media(catalog_key):
    if catalog_key not in catalog_by_key():
        abort(404)
    provider_id = str(json_body().get("provider_id", "")).strip()
    try:
        provider = get_exercise(provider_id)
        get_cached_gif(catalog_key, provider_id)
    except WorkoutXServiceError as error:
        current_app.logger.warning("WorkoutX media approval failed for %s: %s", catalog_key, error)
        return jsonify({"error": "Não foi possível validar esse GIF."}), 422
    review = db.session.get(ExerciseMediaReview, catalog_key)
    if review is None:
        review = ExerciseMediaReview(catalog_key=catalog_key)
        db.session.add(review)
    review.provider_id = provider_id
    review.provider_name = str(provider.get("name", ""))[:200]
    review.provider_equipment = str(provider.get("equipment", ""))[:100] or None
    review.status = "approved"
    review.reviewed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "GIF aprovado.", "review": {
        "provider_id": review.provider_id,
        "provider_name": review.provider_name,
        "provider_equipment": review.provider_equipment,
        "status": review.status,
    }}), 200


@admin_bp.route("/admin/users/<uuid:user_id>/ban", methods=["POST"])
@admin_required
def ban_user(user_id):
    user_to_ban = db.get_or_404(User, user_id)
    if user_to_ban.is_admin:
        return jsonify({"error": "Não é possível banir um administrador."}), 403
    user_to_ban.ban_user()
    db.session.commit()
    return jsonify({"message": f"Usuário {user_to_ban.username} banido com sucesso."}), 200


@admin_bp.route("/admin/users/<uuid:user_id>/unban", methods=["POST"])
@admin_required
def unban_user(user_id):
    user_to_unban = db.get_or_404(User, user_id)
    user_to_unban.unban_user()
    db.session.commit()
    return jsonify({"message": f"Usuário {user_to_unban.username} desbanido com sucesso."}), 200


@admin_bp.route("/admin/users/<uuid:user_id>/premium", methods=["PATCH"])
@admin_required
def update_premium_status(user_id):
    data = json_body()
    is_premium = data.get("is_premium")
    if not isinstance(is_premium, bool):
        return jsonify({"error": "is_premium deve ser verdadeiro ou falso"}), 400

    user_to_update = db.get_or_404(User, user_id)
    user_to_update.is_premium = is_premium
    db.session.commit()
    action = "concedido" if is_premium else "revogado"
    return jsonify({
        "message": f"Acesso Premium {action} para {user_to_update.username}.",
        "user": user_to_update.to_dict(),
    }), 200


@admin_bp.route("/admin/users/<uuid:user_id>/professional", methods=["PATCH"])
@admin_required
def update_professional_status(user_id):
    data = json_body()
    is_professional = data.get("is_professional")
    if not isinstance(is_professional, bool):
        return jsonify({"error": "is_professional deve ser verdadeiro ou falso"}), 400

    user_to_update = db.get_or_404(User, user_id)
    professional_scope = data.get("professional_scope")
    if is_professional:
        plan_code = user_to_update.effective_plan_code()
        allowed_scopes = {"diet", "workout"} if plan_code == "professional_single" else {"both"}
        if plan_code not in {"professional_single", "professional_complete"}:
            allowed_scopes = {"diet", "workout", "both"}
        if professional_scope is None and "both" in allowed_scopes:
            professional_scope = "both"
        if professional_scope not in allowed_scopes:
            return jsonify({"error": "Escolha uma especialidade compatível com o plano profissional."}), 400
        user_to_update.professional_scope = professional_scope
    user_to_update.is_professional = is_professional
    if not is_professional:
        user_to_update.professional_scope = None
        now = datetime.utcnow()
        relationships = ProfessionalStudentRelationship.query.filter(
            ProfessionalStudentRelationship.professional_user_id == user_to_update.id,
            ProfessionalStudentRelationship.status.in_(("active", "pending")),
        ).all()
        for relationship in relationships:
            relationship.status = "revoked"
            relationship.revoked_at = now
            relationship.revoked_by_user_id = g.user.id
    db.session.commit()
    action = "concedido" if is_professional else "revogado"
    return jsonify({
        "message": f"Perfil profissional {action} para {user_to_update.username}.",
        "user": user_to_update.to_dict(),
    }), 200


@admin_bp.route("/admin/users/<uuid:user_id>/toggle_admin", methods=["POST"])
@admin_required
def toggle_admin_status(user_id):
    admin_user = g.user
    user_to_toggle = db.get_or_404(User, user_id)

    if user_to_toggle.id == admin_user.id:
        return jsonify({"error": "Você não pode remover seus próprios privilégios de administrador."}), 403

    demoting = user_to_toggle.is_admin
    if demoting and User.query.filter_by(is_admin=True).count() <= 1:
        return jsonify({"error": "Não é possível remover o último administrador."}), 403

    user_to_toggle.is_admin = not user_to_toggle.is_admin
    db.session.commit()
    status = "promovido a" if user_to_toggle.is_admin else "rebaixado de"
    return jsonify({"message": f"Usuário {user_to_toggle.username} {status} administrador."}), 200


@admin_bp.route("/admin/recent_activity", methods=["GET"])
@admin_required
def get_recent_activity():
    limit = 10
    recent_diet = DietEntry.query.order_by(DietEntry.created_at.desc()).options(joinedload(DietEntry.user)).limit(limit).all()
    recent_measurements = Measurement.query.order_by(Measurement.created_at.desc()).options(joinedload(Measurement.user)).limit(limit).all()
    recent_chats = ChatMessage.query.order_by(ChatMessage.created_at.desc()).options(joinedload(ChatMessage.user)).limit(limit).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(limit).all()

    activities = []
    for d in recent_diet:
        activities.append({"type": "diet", "username": d.user.username, "created_at": d.created_at.isoformat()})
    for m in recent_measurements:
        activities.append({"type": "measurement", "username": m.user.username, "created_at": m.created_at.isoformat()})
    for c in recent_chats:
        activities.append({"type": "chat", "username": c.user.username, "created_at": c.created_at.isoformat()})
    for u in recent_users:
        activities.append({"type": "user", "username": u.username, "created_at": u.created_at.isoformat()})

    activities.sort(key=lambda x: x["created_at"], reverse=True)
    return jsonify(activities[:20]), 200


def _parse_admin_period():
    raw_from = request.args.get("from")
    raw_to = request.args.get("to")
    bucket = request.args.get("bucket", "day").lower().strip()
    legacy_period = request.args.get("period")
    if legacy_period and not raw_from and not raw_to:
        bucket = legacy_period.lower().strip()
    if bucket not in {"day", "week"}:
        bucket = "day"
    try:
        end_date = datetime.fromisoformat(raw_to).date() if raw_to else datetime.utcnow().date()
        start_date = datetime.fromisoformat(raw_from).date() if raw_from else end_date - timedelta(days=29)
    except ValueError:
        abort(400, description="Período inválido.")
    if start_date > end_date:
        abort(400, description="Período inválido.")
    if bucket == "week":
        start_date = start_date - timedelta(days=start_date.weekday())
    return start_date, end_date, bucket


def _bucket_label(day, bucket):
    if bucket == "week":
        end = day + timedelta(days=6)
        return f"{day.strftime('%d/%m')} - {end.strftime('%d/%m')}"
    return day.strftime("%d/%m")


def _bucket_key(moment, bucket):
    if isinstance(moment, datetime):
        moment = moment.date()
    if bucket == "week":
        return moment - timedelta(days=moment.weekday())
    return moment


def _date_series(start_date, end_date, bucket):
    step = timedelta(days=7 if bucket == "week" else 1)
    current = start_date
    items = []
    while current <= end_date:
        items.append(current)
        current += step
    return items


def _admin_summary_counts(users, from_date, to_date):
    user_ids = [user.id for user in users]
    period_start = datetime.combine(from_date, datetime.min.time())
    period_end = datetime.combine(to_date, datetime.max.time())
    total_users = User.query.count()
    active_subscriptions = Subscription.query.filter(
        Subscription.status.in_(("active", "trialing")),
        or_(Subscription.current_period_end.is_(None), Subscription.current_period_end > datetime.utcnow()),
    ).all()
    user_plan_counts = {"premium_student": 0, "professional_single": 0, "professional_complete": 0}
    for subscription in active_subscriptions:
        if subscription.plan_code in user_plan_counts:
            user_plan_counts[subscription.plan_code] += 1
    premium_users = 0
    professional_users = 0
    banned_users = 0
    admin_users = 0
    active_users_ids = set()
    if user_ids:
        recent_diet = DietEntry.query.with_entities(DietEntry.user_id, DietEntry.created_at).filter(
            DietEntry.created_at >= period_start,
            DietEntry.created_at <= period_end,
        ).all()
        recent_measurements = Measurement.query.with_entities(Measurement.user_id, Measurement.created_at).filter(
            Measurement.created_at >= period_start,
            Measurement.created_at <= period_end,
        ).all()
        recent_chats = ChatMessage.query.with_entities(ChatMessage.user_id, ChatMessage.created_at).filter(
            ChatMessage.created_at >= period_start,
            ChatMessage.created_at <= period_end,
        ).all()
        recent_sessions = WorkoutSession.query.with_entities(WorkoutSession.user_id, WorkoutSession.completed_at).filter(
            WorkoutSession.completed_at.isnot(None),
            WorkoutSession.completed_at >= period_start,
            WorkoutSession.completed_at <= period_end,
        ).all()
        for item in recent_diet + recent_measurements + recent_chats + recent_sessions:
            active_users_ids.add(item.user_id)

    for user in users:
        if user.is_admin:
            admin_users += 1
        if user.is_banned:
            banned_users += 1
        if user.has_entitlement("premium"):
            premium_users += 1
        if user.is_professional:
            professional_users += 1

    return {
        "total_users": total_users,
        "new_users": sum(1 for user in users if user.created_at and from_date <= user.created_at.date() <= to_date),
        "active_users": len(active_users_ids),
        "admin_users": admin_users,
        "banned_users": banned_users,
        "premium_users": premium_users,
        "professional_users": professional_users,
        "active_subscriptions": len(active_subscriptions),
        "active_subscription_plans": user_plan_counts,
    }


def _build_admin_analytics_payload(from_date, to_date, bucket):
    users = User.query.order_by(User.created_at.asc()).all()
    summary = _admin_summary_counts(users, from_date, to_date)
    bucket_dates = _date_series(from_date, to_date, bucket)

    user_new_by_bucket = defaultdict(int)
    activity_by_bucket = defaultdict(lambda: {"diet_entries": 0, "measurements": 0, "chat_messages": 0, "workout_sessions": 0, "active_users": set()})
    subscription_by_bucket = defaultdict(lambda: {"premium_student": 0, "professional_single": 0, "professional_complete": 0})

    for user in users:
        if not user.created_at:
            continue
        key = _bucket_key(user.created_at, bucket)
        if from_date <= key <= to_date:
            user_new_by_bucket[key] += 1

    for model, metric_key, date_field in [
        (DietEntry, "diet_entries", DietEntry.created_at),
        (Measurement, "measurements", Measurement.created_at),
        (ChatMessage, "chat_messages", ChatMessage.created_at),
    ]:
        for user_id, created_at in db.session.query(model.user_id, date_field).filter(
            date_field >= datetime.combine(from_date, datetime.min.time()),
            date_field <= datetime.combine(to_date, datetime.max.time()),
        ).all():
            key = _bucket_key(created_at, bucket)
            activity_by_bucket[key][metric_key] += 1
            activity_by_bucket[key]["active_users"].add(user_id)

    for user_id, completed_at in db.session.query(WorkoutSession.user_id, WorkoutSession.completed_at).filter(
        WorkoutSession.completed_at.isnot(None),
        WorkoutSession.completed_at >= datetime.combine(from_date, datetime.min.time()),
        WorkoutSession.completed_at <= datetime.combine(to_date, datetime.max.time()),
    ).all():
        key = _bucket_key(completed_at, bucket)
        activity_by_bucket[key]["workout_sessions"] += 1
        activity_by_bucket[key]["active_users"].add(user_id)

    active_subscriptions = Subscription.query.filter(
        Subscription.status.in_(("active", "trialing")),
        or_(Subscription.current_period_end.is_(None), Subscription.current_period_end > datetime.utcnow()),
    ).all()
    for subscription in active_subscriptions:
        key = _bucket_key(subscription.created_at or datetime.utcnow(), bucket)
        if subscription.plan_code in subscription_by_bucket[key]:
            subscription_by_bucket[key][subscription.plan_code] += 1

    labels = []
    new_users_series = []
    active_users_series = []
    activity_series = []
    subscription_series = []
    for bucket_day in bucket_dates:
        labels.append(_bucket_label(bucket_day, bucket))
        activity = activity_by_bucket.get(bucket_day, {"diet_entries": 0, "measurements": 0, "chat_messages": 0, "workout_sessions": 0, "active_users": set()})
        subs = subscription_by_bucket.get(bucket_day, {"premium_student": 0, "professional_single": 0, "professional_complete": 0})
        new_users_series.append(user_new_by_bucket.get(bucket_day, 0))
        active_users_series.append(len(activity["active_users"]))
        activity_series.append({
            "label": _bucket_label(bucket_day, bucket),
            "diet_entries": activity["diet_entries"],
            "measurements": activity["measurements"],
            "chat_messages": activity["chat_messages"],
            "workout_sessions": activity["workout_sessions"],
            "active_users": len(activity["active_users"]),
        })
        subscription_series.append({
            "label": _bucket_label(bucket_day, bucket),
            "premium_student": subs["premium_student"],
            "professional_single": subs["professional_single"],
            "professional_complete": subs["professional_complete"],
        })

    applications = ProfessionalApplication.query.filter(
        ProfessionalApplication.created_at >= datetime.combine(from_date, datetime.min.time()),
        ProfessionalApplication.created_at <= datetime.combine(to_date, datetime.max.time()),
    ).all()
    application_counts = {"pending": 0, "approved": 0, "rejected": 0}
    for application in applications:
        if application.status in application_counts:
            application_counts[application.status] += 1

    return {
        "range": {"from": from_date.isoformat(), "to": to_date.isoformat(), "bucket": bucket},
        "summary": summary,
        "series": {
            "labels": labels,
            "new_users": new_users_series,
            "active_users": active_users_series,
            "activity": activity_series,
            "subscriptions": subscription_series,
        },
        "breakdowns": {
            "applications": application_counts,
            "subscriptions": summary["active_subscription_plans"],
            "roles": {
                "admins": summary["admin_users"],
                "premium": summary["premium_users"],
                "professionals": summary["professional_users"],
                "banned": summary["banned_users"],
            },
        },
    }


@admin_bp.route("/admin/analytics", methods=["GET"])
@admin_required
def admin_analytics():
    from_date, to_date, bucket = _parse_admin_period()
    return jsonify(_build_admin_analytics_payload(from_date, to_date, bucket)), 200


@admin_bp.route("/admin/analytics.csv", methods=["GET"])
@admin_required
def admin_analytics_csv():
    from_date, to_date, bucket = _parse_admin_period()
    payload = _build_admin_analytics_payload(from_date, to_date, bucket)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["label", "new_users", "active_users", "diet_entries", "measurements", "chat_messages", "workout_sessions", "premium_student", "professional_single", "professional_complete"])
    for idx, item in enumerate(payload["series"]["activity"]):
        sub = payload["series"]["subscriptions"][idx]
        writer.writerow([
            item["label"],
            payload["series"]["new_users"][idx],
            item["active_users"],
            item["diet_entries"],
            item["measurements"],
            item["chat_messages"],
            item["workout_sessions"],
            sub.get("premium_student", 0),
            sub.get("professional_single", 0),
            sub.get("professional_complete", 0),
        ])
    response = current_app.response_class(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = 'attachment; filename="admin-analytics.csv"'
    return response
