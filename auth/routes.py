"""Auth API: register, login, me."""

from flask import Blueprint, request, jsonify, g, current_app, redirect

from auth.models import create_user, get_user_by_username, get_user_by_id, get_user_by_phone, verify_password
from auth.jwt_utils import create_token

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _user_safe(user: dict) -> dict:
    """Return user dict without password_hash for API responses."""
    return {
        "id": user["id"],
        "username": user["username"],
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "phone": user.get("phone"),
        "email": user.get("email"),
    }


def _auth_response(token: str, user: dict):
    """JSON response and set cookie for browser GET /."""
    resp = jsonify({
        "token": token,
        "user": _user_safe(user),
    })
    resp.set_cookie(
        "token",
        token,
        max_age=7 * 24 * 3600,
        path="/",
        httponly=True,
        samesite="Lax",
        secure=current_app.config.get("SESSION_COOKIE_SECURE", False),
    )
    return resp


@bp.route("/register", methods=["POST"])
def register():
    """Create a new user. Body: { username, password, first_name, last_name, phone, email } (all required)."""
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    first_name = (data.get("first_name") or "").strip() or None
    last_name = (data.get("last_name") or "").strip() or None
    phone = (data.get("phone") or "").strip() or None
    email = (data.get("email") or "").strip().lower() or None

    if not first_name:
        return jsonify({"error": "First name is required"}), 400
    if not last_name:
        return jsonify({"error": "Last name is required"}), 400
    if not username:
        return jsonify({"error": "Username is required"}), 400
    if not password:
        return jsonify({"error": "Password is required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if not phone:
        return jsonify({"error": "Phone is required"}), 400
    if not email:
        return jsonify({"error": "Email is required"}), 400
    if get_user_by_phone(phone):
        return jsonify({"error": "Phone number already registered"}), 409

    try:
        user = create_user(
            username, password,
            first_name=first_name, last_name=last_name, phone=phone, email=email,
        )
    except Exception as e:
        current_app.logger.exception("register create_user")
        return jsonify({"error": "Registration failed. Please try again."}), 500
    if user is None:
        return jsonify({"error": "Username already taken"}), 409

    try:
        token = create_token(
            user["id"], user["username"],
            secret=current_app.config.get("JWT_SECRET"),
        )
        resp = _auth_response(token, user)
        resp.status_code = 201
        return resp
    except Exception as e:
        current_app.logger.exception("register token/cookie")
        return jsonify({"error": "Registration failed. Please try again."}), 500


@bp.route("/login", methods=["POST"])
def login():
    """Authenticate and return JWT. Body: { username, password }."""
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    try:
        user = get_user_by_username(username)
    except Exception as e:
        current_app.logger.exception("login get_user")
        return jsonify({"error": "Login failed. Please try again."}), 500
    if user is None or not verify_password(user, password):
        return jsonify({"error": "Invalid username or password"}), 401

    try:
        token = create_token(
            user["id"], user["username"],
            secret=current_app.config.get("JWT_SECRET"),
        )
        return _auth_response(token, user)
    except Exception as e:
        current_app.logger.exception("login token/cookie")
        return jsonify({"error": "Login failed. Please try again."}), 500


@bp.route("/me")
def me():
    """Return current user (requires valid JWT). g.current_user set by app before_request."""
    if not getattr(g, "current_user", None):
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify(_user_safe(g.current_user))


@bp.route("/logout", methods=["POST", "GET"])
def logout():
    """Clear auth cookie and redirect to login."""
    resp = redirect("/login") if request.method == "GET" else jsonify({"ok": True})
    resp.set_cookie("token", "", max_age=0, path="/", httponly=True, samesite="Lax")
    return resp
