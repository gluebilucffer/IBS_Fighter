from __future__ import annotations

import hmac
import sqlite3
from datetime import date, timedelta
from html import escape
from http import HTTPStatus
from urllib.parse import quote

from flask import Flask, Response, jsonify, redirect, request, send_from_directory, session
from werkzeug.middleware.proxy_fix import ProxyFix

from .auth import (
    AuthError,
    build_google_auth_url,
    complete_google_login,
    current_user,
    ensure_csrf_token,
    google_oauth_configured,
    safe_next_path,
)
from .config import (
    AUTH_REQUIRED,
    BACKUP_ADMIN_TOKEN,
    DB_PATH,
    GOOGLE_ALLOWED_EMAILS,
    HOST,
    OPENAI_API_KEY,
    PORT,
    SECRET_KEY,
    SESSION_COOKIE_SECURE,
    SESSION_DAYS,
    STATIC_DIR,
    UPLOADS_DIR,
)
from .crud import build_day_payload, delete_record, fetch_records, insert_record, update_record
from .db import get_connection, init_database
from .drive_backup import backup_to_google_drive
from .models import TABLES
from .openai_meal_analyzer import analyze_meal
from .reports import build_report


def create_app() -> Flask:
    if AUTH_REQUIRED and not SECRET_KEY:
        raise RuntimeError("SECRET_KEY must be set when auth is enabled")

    app = Flask(__name__, static_folder=None)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
    app.secret_key = SECRET_KEY
    app.config.update(
        PREFERRED_URL_SCHEME="https" if SESSION_COOKIE_SECURE else "http",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=SESSION_COOKIE_SECURE,
        PERMANENT_SESSION_LIFETIME=timedelta(days=SESSION_DAYS),
        SESSION_REFRESH_EACH_REQUEST=True,
    )

    init_database()
    register_hooks(app)
    register_routes(app)
    return app


def register_hooks(app: Flask) -> None:
    @app.before_request
    def enforce_auth_and_csrf() -> Response | None:
        if is_public_endpoint():
            return None

        if request.path == "/api/admin/backups/drive" and backup_token_is_valid():
            return None

        user = current_user()
        if AUTH_REQUIRED and not user:
            if request.path.startswith("/api/"):
                return json_error("需要先用 Google 登录", HTTPStatus.UNAUTHORIZED)
            return redirect(f"/login?next={safe_next_path(request.path)}")

        if AUTH_REQUIRED and user:
            session.permanent = True

        if not AUTH_REQUIRED:
            session.setdefault(
                "user",
                {"email": "local-dev@ibs-fighter", "name": "Local Dev", "picture": ""},
            )
            ensure_csrf_token()

        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not csrf_is_valid():
            return json_error("CSRF token 无效或缺失", HTTPStatus.FORBIDDEN)

        return None


def register_routes(app: Flask) -> None:
    @app.get("/healthz")
    def healthz() -> Response:
        return jsonify(
            {
                "ok": True,
                "database": str(DB_PATH),
                "auth_required": AUTH_REQUIRED,
            }
        )

    @app.get("/login")
    def login_page() -> Response:
        next_path = safe_next_path(request.args.get("next"))
        if AUTH_REQUIRED and current_user():
            return redirect(next_path)
        return Response(login_html(next_path), mimetype="text/html; charset=utf-8")

    @app.get("/auth/google/start")
    def google_auth_start() -> Response:
        try:
            return redirect(build_google_auth_url(request.args.get("next") or "/"))
        except AuthError as exc:
            return Response(error_html("Google OAuth 未配置", str(exc)), status=500)

    @app.get("/auth/google/callback")
    def google_auth_callback() -> Response:
        try:
            complete_google_login(
                code=request.args.get("code", ""),
                state=request.args.get("state", ""),
            )
        except AuthError as exc:
            return Response(error_html("登录失败", str(exc)), status=403)
        next_path = safe_next_path(session.pop("post_login_next", "/"))
        return redirect(next_path)

    @app.get("/logout")
    def logout() -> Response:
        session.clear()
        return redirect("/login")

    @app.get("/api/auth/me")
    def api_auth_me() -> Response:
        user = current_user()
        if AUTH_REQUIRED and not user:
            return json_error("需要先用 Google 登录", HTTPStatus.UNAUTHORIZED)
        if not user:
            user = {"email": "local-dev@ibs-fighter", "name": "Local Dev", "picture": ""}
            session["user"] = user
        return jsonify(
            {
                "user": user,
                "csrf_token": ensure_csrf_token(),
                "ai_meal_enabled": bool(OPENAI_API_KEY),
            }
        )

    @app.get("/")
    def index() -> Response:
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/uploads/<path:filename>")
    def uploaded_file(filename: str) -> Response:
        return send_from_directory(UPLOADS_DIR, filename)

    @app.get("/api/day")
    def api_day() -> Response:
        selected_date = request.args.get("date", date.today().isoformat())
        return jsonify(build_day_payload(selected_date))

    @app.get("/api/report")
    def api_report() -> Response:
        selected_end = request.args.get("end_date", date.today().isoformat())
        module = request.args.get("module", "bowel")
        try:
            days = int(request.args.get("days", "7"))
            with get_connection() as conn:
                return jsonify(build_report(conn, module, selected_end, days))
        except ValueError as exc:
            return json_error(str(exc), HTTPStatus.BAD_REQUEST)

    @app.route("/api/ai/meals/analyze", methods=["POST"])
    def api_ai_meals_analyze() -> Response:
        try:
            return jsonify(analyze_meal(read_json_body()))
        except ValueError as exc:
            return json_error(str(exc), HTTPStatus.BAD_REQUEST)
        except RuntimeError as exc:
            return json_error(str(exc), HTTPStatus.BAD_GATEWAY)

    @app.post("/api/admin/backups/drive")
    def api_drive_backup() -> Response:
        try:
            return jsonify(backup_to_google_drive())
        except RuntimeError as exc:
            return json_error(str(exc), HTTPStatus.BAD_REQUEST)

    @app.get("/api/<table>")
    def api_table_records(table: str) -> Response:
        if table not in TABLES:
            return json_error("未知数据表", HTTPStatus.NOT_FOUND)
        return jsonify({"items": fetch_records(table, request.args.get("date"))})

    @app.post("/api/<table>")
    def api_insert_record(table: str) -> Response:
        if table not in TABLES:
            return json_error("未知数据表", HTTPStatus.NOT_FOUND)
        try:
            return jsonify(insert_record(table, read_json_body())), HTTPStatus.CREATED
        except (sqlite3.IntegrityError, ValueError) as exc:
            return json_error(str(exc), HTTPStatus.BAD_REQUEST)

    @app.route("/api/<table>/<int:record_id>", methods=["PUT", "PATCH"])
    def api_update_record(table: str, record_id: int) -> Response:
        if table not in TABLES:
            return json_error("未知数据表", HTTPStatus.NOT_FOUND)
        try:
            return jsonify(update_record(table, record_id, read_json_body()))
        except LookupError as exc:
            return json_error(str(exc), HTTPStatus.NOT_FOUND)
        except (sqlite3.IntegrityError, ValueError) as exc:
            return json_error(str(exc), HTTPStatus.BAD_REQUEST)

    @app.delete("/api/<table>/<int:record_id>")
    def api_delete_record(table: str, record_id: int) -> Response:
        if table not in TABLES:
            return json_error("未知数据表", HTTPStatus.NOT_FOUND)
        try:
            delete_record(table, record_id)
            return jsonify({"ok": True})
        except sqlite3.IntegrityError:
            return json_error("这条药物已经有用药记录，不能直接删除", HTTPStatus.BAD_REQUEST)
        except LookupError as exc:
            return json_error(str(exc), HTTPStatus.NOT_FOUND)

    @app.get("/<path:filename>")
    def static_file(filename: str) -> Response:
        return send_from_directory(STATIC_DIR, filename)


def is_public_endpoint() -> bool:
    return request.endpoint in {
        "healthz",
        "login_page",
        "google_auth_start",
        "google_auth_callback",
        "logout",
    }


def csrf_is_valid() -> bool:
    if request.path == "/api/admin/backups/drive" and backup_token_is_valid():
        return True
    expected = session.get("csrf_token")
    provided = request.headers.get("X-CSRF-Token", "")
    return bool(expected and provided and hmac.compare_digest(str(expected), provided))


def backup_token_is_valid() -> bool:
    if not BACKUP_ADMIN_TOKEN:
        return False
    provided = request.headers.get("X-Backup-Token") or request.headers.get("Authorization", "")
    if provided.startswith("Bearer "):
        provided = provided.removeprefix("Bearer ").strip()
    return bool(provided and hmac.compare_digest(provided, BACKUP_ADMIN_TOKEN))


def read_json_body() -> dict:
    payload = request.get_json(silent=True)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("请求体必须是 JSON 对象")
    return payload


def json_error(message: str, status: HTTPStatus) -> tuple[Response, int]:
    return jsonify({"error": message}), int(status)


def login_html(next_path: str = "/") -> str:
    allowed = escape(", ".join(sorted(GOOGLE_ALLOWED_EMAILS)) or "未配置")
    login_next = quote(safe_next_path(next_path), safe="")
    disabled = "" if google_oauth_configured() else "disabled"
    button_label = "使用 Google 登录" if google_oauth_configured() else "Google OAuth 未配置"
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>IBS Fighter Login</title>
    <style>
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #f7f4ee;
        color: #17211f;
        font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
      }}
      main {{
        width: min(420px, calc(100vw - 32px));
        display: grid;
        gap: 18px;
        padding: 28px;
        border: 1px solid #ddd8ce;
        border-radius: 8px;
        background: #fffaf1;
      }}
      h1 {{ margin: 0; color: #093f3a; }}
      p {{ margin: 0; color: #66736f; line-height: 1.5; }}
      a, button {{
        min-height: 44px;
        display: inline-grid;
        place-items: center;
        border: 0;
        border-radius: 8px;
        background: #0f5f56;
        color: white;
        font: inherit;
        font-weight: 760;
        text-decoration: none;
      }}
      button:disabled {{
        background: #66736f;
        cursor: not-allowed;
      }}
      small {{ color: #66736f; }}
    </style>
  </head>
  <body>
    <main>
      <div>
        <h1>IBS Fighter</h1>
        <p>公网访问已启用 Google 登录保护。</p>
      </div>
      {"<a href='/auth/google/start?next=" + login_next + "'>" + button_label + "</a>" if not disabled else "<button disabled>" + button_label + "</button>"}
      <small>允许账号：{allowed}</small>
    </main>
  </body>
</html>"""


def error_html(title: str, detail: str) -> str:
    title = escape(title)
    detail = escape(detail)
    return f"""<!doctype html>
<html lang="zh-CN">
  <head><meta charset="utf-8" /><title>{title}</title></head>
  <body>
    <h1>{title}</h1>
    <p>{detail}</p>
    <p><a href="/login">返回登录</a></p>
  </body>
</html>"""


def main() -> None:
    app = create_app()
    print(f"IBS Fighter running at http://{HOST}:{PORT}")
    print(f"SQLite database: {DB_PATH}")
    app.run(host=HOST, port=PORT)
