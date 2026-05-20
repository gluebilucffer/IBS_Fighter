export const tableLabels = {
  bowel_movements: "排便",
  meals: "饮食",
  medications: "用药",
  medication_products: "药物",
  exercises: "运动",
};

export const trackingTables = ["bowel_movements", "meals", "medications", "exercises"];

export const tableFields = {
  bowel_movements: [
    "id",
    "occurred_at",
    "bristol_type",
    "location",
    "urgency",
    "color",
    "notes",
  ],
  meals: [
    "id",
    "eaten_at",
    "meal_type",
    "location",
    "foods",
    "photo_path",
    "photo_filename",
    "symptoms_after",
    "notes",
  ],
  medications: [
    "id",
    "taken_at",
    "product_id",
    "quantity_value",
    "quantity_unit",
    "timing_relation",
    "notes",
  ],
  medication_products: ["id", "product_name", "ingredients", "product_type", "default_unit"],
  exercises: [
    "id",
    "started_at",
    "activity_type",
    "duration_minutes",
    "intensity",
    "notes",
  ],
};

export const numericFields = new Set([
  "bristol_type",
  "urgency",
  "product_id",
  "quantity_value",
  "duration_minutes",
]);

export const bristolLabels = {
  1: "1 硬球状",
  2: "2 结块香肠状",
  3: "3 表面裂纹",
  4: "4 光滑柔软",
  5: "5 软块",
  6: "6 糊状",
  7: "7 水样",
};
