import { numericFields, tableFields } from "./constants.js";
import { populateMedicationPickers } from "./records.js";
import { state } from "./state.js";
import { defaultDateTime, today } from "./utils.js";


export async function collectFormData(form) {
  const formData = new FormData(form);
  const payload = {};
  formData.forEach((value, key) => {
    if (key === "id" || key === "photo") return;
    const trimmed = typeof value === "string" ? value.trim() : value;
    if (trimmed === "") {
      payload[key] = null;
    } else if (numericFields.has(key)) {
      payload[key] = Number(trimmed);
    } else {
      payload[key] = trimmed;
    }
  });

  const photoInput = getControl(form, "photo");
  if (photoInput?.files?.[0]) {
    payload.photo_filename = photoInput.files[0].name;
    payload.photo_data_url = await fileToDataUrl(photoInput.files[0]);
  }

  return payload;
}


export function collectMedicationPayloads(form) {
  const checkedProducts = [...form.querySelectorAll('input[name="product_ids"]:checked')];
  if (!checkedProducts.length) {
    throw new Error("请至少选择一种药物");
  }

  return checkedProducts.map((checkbox) => {
    const productId = Number(checkbox.value);
    const product = state.medicationProducts.find((item) => Number(item.id) === productId);
    const quantityValue = getControl(form, `quantity_value_${productId}`)?.value.trim();
    return {
      taken_at: getControl(form, "taken_at").value,
      product_id: productId,
      quantity_value: quantityValue === "" ? null : Number(quantityValue),
      quantity_unit: product?.default_unit || null,
      timing_relation: getControl(form, "timing_relation")?.value || null,
      notes: getControl(form, "notes").value.trim() || null,
    };
  });
}


export function fillForm(table, record) {
  const form = document.querySelector(`[data-form="${table}"]`);
  if (table === "medications") {
    getControl(form, "id").value = record.id ?? "";
    getControl(form, "taken_at").value = record.taken_at ?? "";
    const timingControl = getControl(form, "timing_relation");
    if (timingControl) timingControl.value = record.timing_relation ?? "";
    getControl(form, "notes").value = record.notes ?? "";
    populateMedicationPickers(record);
    form.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }

  tableFields[table].forEach((field) => {
    const input = getControl(form, field);
    if (!input) return;
    input.value = record[field] ?? "";
  });
  form.scrollIntoView({ behavior: "smooth", block: "start" });
}


export function resetForm(table) {
  const form = document.querySelector(`[data-form="${table}"]`);
  form.reset();
  getControl(form, "id").value = "";
  setFormDefaultDateTime(form);
  if (table === "bowel_movements") {
    getControl(form, "bristol_type").value = "4";
    getControl(form, "urgency").value = "0";
  }
  if (table === "meals") {
    getControl(form, "symptoms_after").value = "无明显反应";
  }
  if (table === "medications" || table === "medication_products") {
    populateMedicationPickers();
  }
}


export function setEmptyFormDefaults() {
  document.querySelectorAll("form").forEach((form) => {
    if (!getControl(form, "id")?.value) setFormDefaultDateTime(form);
  });
}


function setFormDefaultDateTime(form) {
  form.querySelectorAll('input[type="datetime-local"]').forEach((input) => {
    input.value = defaultDateTime();
  });
  form.querySelectorAll('input[type="date"]').forEach((input) => {
    input.value = state.date || today();
  });
}


function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("照片读取失败"));
    reader.readAsDataURL(file);
  });
}


function getControl(form, name) {
  return form.elements.namedItem(name);
}
