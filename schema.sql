PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS bowel_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    occurred_timezone TEXT,
    occurred_at_utc TEXT,
    bristol_type INTEGER NOT NULL CHECK (bristol_type BETWEEN 1 AND 7),
    location TEXT,
    urgency INTEGER CHECK (urgency IS NULL OR urgency BETWEEN 0 AND 5),
    color TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    eaten_at TEXT NOT NULL,
    eaten_timezone TEXT,
    eaten_at_utc TEXT,
    meal_type TEXT,
    location TEXT,
    foods TEXT,
    photo_path TEXT,
    photo_filename TEXT,
    symptoms_after TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS medication_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    ingredients TEXT,
    product_type TEXT NOT NULL,
    default_unit TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(product_name, product_type)
);

CREATE TABLE IF NOT EXISTS medications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    taken_at TEXT NOT NULL,
    taken_timezone TEXT,
    taken_at_utc TEXT,
    product_id INTEGER NOT NULL REFERENCES medication_products(id) ON DELETE RESTRICT,
    quantity_value REAL,
    quantity_unit TEXT,
    timing_relation TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    started_timezone TEXT,
    started_at_utc TEXT,
    activity_type TEXT NOT NULL,
    duration_minutes INTEGER CHECK (duration_minutes IS NULL OR duration_minutes >= 0),
    intensity TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bowel_movements_occurred_at ON bowel_movements (occurred_at);
CREATE INDEX IF NOT EXISTS idx_meals_eaten_at ON meals (eaten_at);
CREATE INDEX IF NOT EXISTS idx_medication_products_name ON medication_products (product_name);
CREATE INDEX IF NOT EXISTS idx_medications_taken_at ON medications (taken_at);
CREATE INDEX IF NOT EXISTS idx_exercises_started_at ON exercises (started_at);

CREATE TRIGGER IF NOT EXISTS trg_bowel_movements_updated_at
AFTER UPDATE ON bowel_movements
FOR EACH ROW
BEGIN
    UPDATE bowel_movements SET updated_at = datetime('now') WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_meals_updated_at
AFTER UPDATE ON meals
FOR EACH ROW
BEGIN
    UPDATE meals SET updated_at = datetime('now') WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_medications_updated_at
AFTER UPDATE ON medications
FOR EACH ROW
BEGIN
    UPDATE medications SET updated_at = datetime('now') WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_medication_products_updated_at
AFTER UPDATE ON medication_products
FOR EACH ROW
BEGIN
    UPDATE medication_products SET updated_at = datetime('now') WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_exercises_updated_at
AFTER UPDATE ON exercises
FOR EACH ROW
BEGIN
    UPDATE exercises SET updated_at = datetime('now') WHERE id = OLD.id;
END;
