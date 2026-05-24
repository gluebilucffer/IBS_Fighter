let csrfToken = "";


export function setCsrfToken(token) {
  csrfToken = token || "";
}


export async function requestJson(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (csrfToken && !["GET", "HEAD", "OPTIONS"].includes(method)) {
    headers.set("X-CSRF-Token", csrfToken);
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });
  const payload = await response.json().catch(() => ({}));
  if (response.status === 401) {
    const next = encodeURIComponent(`${window.location.pathname}${window.location.search}`);
    window.location.href = `/login?next=${next}`;
    throw new Error("需要先用 Google 登录");
  }
  if (!response.ok) {
    throw new Error(payload.error || "请求失败");
  }
  return payload;
}
