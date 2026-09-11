import re
import unicodedata


def _normalized(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).lower().split())


def meal_slot_key(meal_type, order=None):
    label = _normalized(meal_type)
    if "cafe" in label and "manha" in label:
        return "breakfast"
    if "almoco" in label:
        return "lunch"
    if "jantar" in label:
        return "dinner"
    if "ceia" in label:
        return "supper"
    if "lanche" in label:
        base = "snack"
        if "manha" in label:
            base = "morning_snack"
        elif "tarde" in label:
            base = "afternoon_snack"
        elif "noite" in label:
            base = "evening_snack"
        return f"{base}_{int(order)}" if order is not None else base
    slug = re.sub(r"[^a-z0-9]+", "_", label).strip("_") or "meal"
    return slug[:64]


def plan_day_number(day_label):
    match = re.fullmatch(r"\s*dia\s+(\d+)\s*", _normalized(day_label))
    return int(match.group(1)) if match else None
