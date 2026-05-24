from __future__ import annotations


TRACKING_TABLES = [
    "bowel_movements",
    "meals",
    "medications",
    "exercises",
]


TABLES = {
    "bowel_movements": {
        "date_column": "occurred_at",
        "fields": {
            "occurred_at": "text",
            "occurred_timezone": "text",
            "occurred_at_utc": "text",
            "bristol_type": "int",
            "location": "text",
            "urgency": "int",
            "color": "text",
            "notes": "text",
        },
        "computed_fields": {"occurred_timezone", "occurred_at_utc"},
        "required": {"occurred_at", "bristol_type"},
        "order": "occurred_at ASC, id ASC",
    },
    "meals": {
        "date_column": "eaten_at",
        "fields": {
            "eaten_at": "text",
            "eaten_timezone": "text",
            "eaten_at_utc": "text",
            "meal_type": "text",
            "location": "text",
            "foods": "text",
            "photo_path": "text",
            "photo_filename": "text",
            "symptoms_after": "text",
            "notes": "text",
        },
        "computed_fields": {"eaten_timezone", "eaten_at_utc"},
        "required": {"eaten_at"},
        "order": "eaten_at ASC, id ASC",
    },
    "medications": {
        "date_column": "taken_at",
        "fields": {
            "taken_at": "text",
            "taken_timezone": "text",
            "taken_at_utc": "text",
            "product_id": "int",
            "quantity_value": "float",
            "quantity_unit": "text",
            "timing_relation": "text",
            "notes": "text",
        },
        "computed_fields": {"taken_timezone", "taken_at_utc"},
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
            "started_timezone": "text",
            "started_at_utc": "text",
            "activity_type": "text",
            "duration_minutes": "int",
            "intensity": "text",
            "notes": "text",
        },
        "computed_fields": {"started_timezone", "started_at_utc"},
        "required": {"started_at", "activity_type"},
        "order": "started_at ASC, id ASC",
    },
}
