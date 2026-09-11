from src.models.user import Measurement


def body_summary(user_id):
    query = Measurement.query.filter_by(user_id=user_id).order_by(
        Measurement.date.desc(), Measurement.created_at.desc(), Measurement.id.desc()
    )
    latest = query.first()
    metrics = {}
    for field in ("weight", "height", "body_fat", "muscle_mass", "waist", "chest", "arm", "thigh"):
        records = query.filter(getattr(Measurement, field).isnot(None)).limit(2).all()
        values = [{"value": getattr(item, field), "date": item.date.isoformat()} for item in records]
        metrics[field] = {
            "latest": values[0] if values else None,
            "previous": values[1] if len(values) > 1 else None,
            "change": round(values[0]["value"] - values[1]["value"], 1) if len(values) > 1 else None,
        }
    return {"latest_date": latest.date.isoformat() if latest else None, "metrics": metrics}
