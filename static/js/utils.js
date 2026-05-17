export function today() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function defaultDateTime() {
  const now = new Date();
  const datePart = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
  const time = now.toTimeString().slice(0, 5);
  return `${datePart}T${time}`;
}

export function showToast(message) {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("visible"), 2200);
}

export function formatDateTime(value) {
  if (!value) return "";
  return value.replace("T", " ").slice(0, 16);
}

export function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    const map = {
      "&": "&amp;",
      "<": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    };
    if (char === "<") return "&lt;";
    return map[char];
  });
}

export function shortDate(value) {
  if (!value) return "";
  return value.slice(5).replace("-", "/");
}

export function shortText(value, maxLength) {
  if (!value) return "";
  const text = String(value);
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}

export function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return Number.isInteger(number) ? String(number) : number.toFixed(1);
}
