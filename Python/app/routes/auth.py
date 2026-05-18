"""
app/routes/auth.py
Authentication routes: login, register, logout.

Security hardening
──────────────────
  • Rate limiting: 5 attempts / 15 min on /auth, 10 / hour on /api/register
  • Generic error messages on login (no username enumeration)
  • Passwords validated server-side before hashing
  • Email domain whitelist enforced in register
  • Session regenerated after login (session fixation mitigation)
  • Audit events written to MongoDB on success AND failure
"""

from flask import (
    Blueprint, request, jsonify, redirect,
    session, render_template, flash,
)
from werkzeug.security import generate_password_hash, check_password_hash

from app.db import get_db, dict_cursor
from app.extensions import limiter
from app.utils import (
    validate_email, validate_password, validate_nombre, validate_rol,
    registrar_auditoria_mongo,
)

auth_bp = Blueprint("auth", __name__)

# ── Pages ─────────────────────────────────────────────────────────────────

@auth_bp.route("/login")
def login_page():
    if "user_id" in session:
        return redirect("/home")
    return render_template("login.html")


@auth_bp.route("/register")
def register_page():
    if "user_id" in session:
        return redirect("/home")
    return render_template("registro.html")


@auth_bp.route("/logout")
def logout():
    user_id = session.get("user_id")
    registrar_auditoria_mongo("LOGOUT", "Auth", "Usuario cerró sesión", usuario_id=user_id)
    session.clear()
    flash("Sesión cerrada exitosamente", "info")
    return redirect("/login")


# ── Login API ─────────────────────────────────────────────────────────────

@auth_bp.route("/auth", methods=["POST"])
@limiter.limit("5 per 15 minutes")  # brute-force guard
def login():
    """Authenticate user credentials and create a session."""
    # ── Input validation ──
    try:
        correo = validate_email(request.form.get("correo", ""))
    except ValueError:
        return jsonify({"ok": False, "msg": "Credenciales inválidas"}), 400

    contrasena = request.form.get("contrasena", "")
    if not contrasena or len(contrasena) > 128:
        return jsonify({"ok": False, "msg": "Credenciales inválidas"}), 400

    rol_seleccionado = request.form.get("rol", "")

    db = get_db()
    cur = dict_cursor(db)

    try:
        cur.execute(
            """
            SELECT u.*, r.nombre_rol
            FROM usuario u
            JOIN rol r ON r.id_rol = u.id_rol
            WHERE u.correo = %s
            LIMIT 1
            """,
            (correo,),
        )
        user = cur.fetchone()

        # Generic message — do NOT reveal whether the email exists
        _fail_msg = "Credenciales incorrectas o rol no coincide"

        if not user or not check_password_hash(user["contrasena"], contrasena):
            registrar_auditoria_mongo(
                "LOGIN_FAIL", "Auth",
                f"Intento fallido para {correo}",
                extra={"ip": request.remote_addr},
            )
            return jsonify({"ok": False, "msg": _fail_msg}), 401

        if rol_seleccionado and user["nombre_rol"] != rol_seleccionado:
            registrar_auditoria_mongo(
                "LOGIN_FAIL", "Auth",
                f"Rol incorrecto para {correo}",
                extra={"ip": request.remote_addr},
            )
            return jsonify({"ok": False, "msg": _fail_msg}), 401

        # ── Session fixation mitigation ──
        session.clear()

        session["user_id"] = user["id_usuario"]
        session["nombre"]  = user["nombre"]
        session["rol"]     = user["nombre_rol"]
        session.permanent  = True

        # Log success to MySQL
        cur.execute(
            "INSERT INTO log_acciones (id_usuario, accion) VALUES (%s, %s)",
            (user["id_usuario"], f"Login desde {request.remote_addr}"),
        )
        db.commit()

        # Audit MongoDB
        registrar_auditoria_mongo(
            "LOGIN_OK", "Auth",
            f"Acceso exitoso de {correo}",
            usuario_id=user["id_usuario"],
        )

        return jsonify({"ok": True, "redirect": "/home"})

    except Exception as exc:
        print(f"[AUTH] Login error: {exc}")
        return jsonify({"ok": False, "msg": "Error en el servidor"}), 500
    finally:
        cur.close()
        db.close()


# ── Register API ──────────────────────────────────────────────────────────

@auth_bp.route("/api/register", methods=["POST"])
@limiter.limit("10 per hour")   # spam guard
def register():
    """Create a new user account with server-side validation."""
    errors = []

    try:
        nombre = validate_nombre(request.form.get("nombre", ""))
    except ValueError as e:
        errors.append(str(e))

    try:
        correo = validate_email(request.form.get("correo", ""))
    except ValueError as e:
        errors.append(str(e))

    try:
        contrasena = validate_password(request.form.get("contrasena", ""))
    except ValueError as e:
        errors.append(str(e))

    try:
        rol = validate_rol(request.form.get("rol", "Estudiante"))
    except ValueError as e:
        errors.append(str(e))

    if errors:
        return jsonify({"ok": False, "msg": " | ".join(errors)}), 400

    db = get_db()
    cur = dict_cursor(db)

    try:
        cur.execute("SELECT id_rol FROM rol WHERE nombre_rol = %s LIMIT 1", (rol,))
        row = cur.fetchone()
        if not row:
            return jsonify({"ok": False, "msg": "Rol inválido"}), 400
        id_rol = row["id_rol"]

        hashed = generate_password_hash(contrasena)

        cur.execute(
            "INSERT INTO usuario (id_rol, nombre, correo, contrasena) VALUES (%s,%s,%s,%s)",
            (id_rol, nombre, correo, hashed),
        )
        db.commit()

        registrar_auditoria_mongo(
            "REGISTER", "Auth",
            f"Nuevo usuario registrado: {correo}",
            extra={"rol": rol},
        )

        return jsonify({"ok": True, "msg": "Usuario creado exitosamente"})

    except Exception as exc:
        import mysql.connector
        if isinstance(exc, mysql.connector.IntegrityError):
            return jsonify({"ok": False, "msg": "El correo ya está registrado"}), 409
        print(f"[AUTH] Register error: {exc}")
        return jsonify({"ok": False, "msg": "Error al crear usuario"}), 500
    finally:
        cur.close()
        db.close()
