"""
app/utils/security.py
Input validation / sanitisation helpers and the MongoDB audit logger.

Security philosophy implemented here
─────────────────────────────────────
  1. Whitelist, not blacklist — accept only the exact shapes we expect.
  2. Size limits on every field — block oversized payloads early.
  3. Pattern enforcement — emails, times, dates, states.
  4. No raw exception details leak to the client — log server-side only.
  5. MongoDB audit helper swallows its own exceptions so a Mongo outage
     never breaks the main request path.
"""

import re
import html
from datetime import datetime
from flask import request, session


# ── Field size caps ───────────────────────────────────────────────────────

MAX_NOMBRE      = 120
MAX_CORREO      = 254   # RFC 5321
MAX_CONTRASENA  = 128
MAX_DESCRIPCION = 500
MAX_GENERIC     = 100

# ── Whitelisted values ────────────────────────────────────────────────────

VALID_ROLES   = {"Estudiante", "Docente", "Administrador"}
VALID_ESTADOS = {"Disponible", "Ocupado", "Mantenimiento"}

# ── Compiled patterns ─────────────────────────────────────────────────────

_RE_EMAIL = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_RE_TIME  = re.compile(r"^\d{2}:\d{2}$")
_RE_DATE  = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ── Helpers ───────────────────────────────────────────────────────────────

def _strip(value, max_len: int) -> str:
    """Strip whitespace, escape HTML entities, enforce max length."""
    if not isinstance(value, str):
        return ""
    value = html.escape(value.strip())
    return value[:max_len]


def validate_email(raw: str) -> str:
    """Return sanitised email or raise ValueError."""
    val = _strip(raw, MAX_CORREO).lower()
    if not _RE_EMAIL.match(val):
        raise ValueError("Correo electrónico inválido.")
    return val


def validate_password(raw: str) -> str:
    """
    Enforce minimum password policy:
      • 8–128 characters
      • at least one uppercase letter
      • at least one digit
    """
    if not isinstance(raw, str):
        raise ValueError("Contraseña inválida.")
    pw = raw[:MAX_CONTRASENA]            # hard cap — don't even hash huge strings
    if len(pw) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    if not re.search(r"[A-Z]", pw):
        raise ValueError("La contraseña debe tener al menos una letra mayúscula.")
    if not re.search(r"[0-9]", pw):
        raise ValueError("La contraseña debe tener al menos un número.")
    return pw


def validate_nombre(raw: str) -> str:
    val = _strip(raw, MAX_NOMBRE)
    if len(val) < 2:
        raise ValueError("El nombre debe tener al menos 2 caracteres.")
    return val


def validate_rol(raw: str) -> str:
    val = _strip(raw, MAX_GENERIC)
    if val not in VALID_ROLES:
        raise ValueError(f"Rol inválido. Valores permitidos: {VALID_ROLES}")
    return val


def validate_estado(raw: str) -> str:
    val = _strip(raw, MAX_GENERIC)
    if val not in VALID_ESTADOS:
        raise ValueError(f"Estado inválido. Valores permitidos: {VALID_ESTADOS}")
    return val


def validate_time(raw: str) -> str:
    val = _strip(raw, 5)
    if not _RE_TIME.match(val):
        raise ValueError("Formato de hora inválido (HH:MM).")
    return val


def validate_date(raw: str) -> str:
    val = _strip(raw, 10)
    if not _RE_DATE.match(val):
        raise ValueError("Formato de fecha inválido (YYYY-MM-DD).")
    return val


def validate_descripcion(raw: str) -> str:
    return _strip(raw or "", MAX_DESCRIPCION)


def validate_capacidad(raw) -> int:
    try:
        cap = int(raw)
    except (TypeError, ValueError):
        raise ValueError("Capacidad debe ser un número entero.")
    if cap < 0 or cap > 9999:
        raise ValueError("Capacidad fuera de rango (0–9999).")
    return cap


# ── MongoDB audit logger ──────────────────────────────────────────────────

def registrar_auditoria_mongo(
    accion: str,
    modulo: str,
    descripcion: str,
    usuario_id=None,
    extra: dict = None,
):
    """
    Insert an audit document into MongoDB audit_logs collection.
    Safe to call from any route — exceptions are caught and printed so a
    Mongo outage never breaks the main application flow.
    """
    try:
        from app.db import get_mongo
        mongo = get_mongo()
        mongo.audit_logs.insert_one({
            "accion":      _strip(accion, 60),
            "modulo":      _strip(modulo, 60),
            "descripcion": _strip(descripcion, MAX_DESCRIPCION),
            "usuario_id":  usuario_id,
            "ip":          request.remote_addr,
            "fecha":       datetime.utcnow(),
            "extra":       extra or {},
        })
    except Exception as exc:
        print(f"[AUDIT-MONGO] ERROR registrando auditoría: {exc}")


# ── MySQL historial helper ────────────────────────────────────────────────

def registrar_historial(db, id_espacio, estado_anterior, estado_nuevo, user_id):
    """Insert a row into the MySQL historial table."""
    cur = db.cursor()
    try:
        cur.execute(
            """
            INSERT INTO historial (
                id_espacio, estado_anterior, estado_nuevo,
                fecha_cambio, hora_cierre, hora_cambio,
                fecha_creacion, fecha_modificacion, responsable_cambio
            ) VALUES (%s, %s, %s, NOW(), NULL, NULL, NOW(), NOW(), %s)
            """,
            (id_espacio, estado_anterior[:200], estado_nuevo[:200], user_id),
        )
    except Exception as exc:
        print(f"[HISTORIAL] ERROR: {exc}")
    finally:
        cur.close()
