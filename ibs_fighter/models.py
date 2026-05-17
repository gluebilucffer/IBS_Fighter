from __future__ import annotations


TRACKING_TABLES = [
    "bowel_movements",
    "meals",
    "medications",
    "exercises",
    "sleep_entries",
]


TABLES = {
    "bowel_movements": {
        "date_column": "occurred_at",
        "fields": {
            "occurred_at": "text",
            "bristol_type": "int",
            "location": "text",
            "urgency": "int",
            "color": "text",
            "notes": "text",
        },
        "required": {"occurred_at", "bristol_type"},
        "order": "occurred_at ASC, id ASC",
    },
    "meals": {
        "date_column": "eaten_at",
        "fields": {
            "eaten_at": "text",
            "meal_type": "text",
            "location": "text",
            "foods": "text",
            "photo_path": "text",
            "photo_filename": "text",
            "symptoms_after": "text",
            "notes": "text",
        },
        "required": {"eaten_at"},
        "order": "eaten_at ASC, id ASC",
    },
    "medications": {
        "date_column": "taken_at",
        "fields": {
            "taken_at": "text",
            "product_id": "int",
            "quantity_value": "float",
            "quantity_unit": "text",
            "timing_relation": "text",
            "notes": "text",
        },
        "required": {"taken_at", "product_id"},
        "order": "taken_at ASC, id ASC",
    },
    "medication_products": {
        "date_column": None,
        "fields": {
            "product_name": "text",
            "ingredients": "text",
            "product_type": "text",
            "default_unit": "text",
        },
        "required": {"product_name", "product_type", "default_unit"},
        "order": "product_name COLLATE NOCASE ASC, id ASC",
    },
    "exercises": {
        "date_column": "started_at",
        "fields": {
            "started_at": "text",
            "activity_type": "text",
            "duration_minutes": "int",
            "intensity": "text",
            "notes": "text",
        },
        "required": {"started_at", "activity_type"},
        "order": "started_at ASC, id ASC",
    },
    "sleep_entries": {
        "date_column": "sleep_date",
        "fields": {
            "sleep_date": "text",
            "source": "text",
            "started_at": "text",
            "ended_at": "text",
            "duration_minutes": "int",
            "quality": "text",
            "notes": "text",
        },
        "required": {"sleep_date"},
        "order": "sleep_date ASC, id ASC",
    },
}
