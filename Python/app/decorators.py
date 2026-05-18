"""
app/decorators.py
Route protection decorators.

  @login_required      — any authenticated user
  @admin_required      — Administrador role only
  @role_required(...)  — one or more role names (string match)
"""

from functools import wraps
from flask import session, redirect, flash, jsonify, request


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"ok": False, "msg": "No autenticado"}), 401
            flash("Debes iniciar sesión", "warning")
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"ok": False, "msg": "No autenticado"}), 401
            return redirect("/login")
        if session.get("rol") != "Administrador":
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"ok": False, "msg": "Permisos insuficientes"}), 403
            flash("No tienes permisos de administrador", "danger")
            return redirect("/")
        return f(*args, **kwargs)
    return wrapper


def role_required(*roles):
    """Accept role names as strings, e.g. @role_required('Docente', 'Administrador')."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Debes iniciar sesión", "warning")
                return redirect("/login")
            if session.get("rol") not in roles:
                flash("No tienes permiso para acceder a esta sección.", "danger")
                return redirect("/home")
            return f(*args, **kwargs)
        return wrapper
    return decorator
