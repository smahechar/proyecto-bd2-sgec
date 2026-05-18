"""
app/routes/admin.py
Admin-only data endpoints: historial HTML, all reservations, user list,
and the dashboard statistics endpoint.

Security notes
──────────────
  • Historial HTML is generated server-side with html.escape() to avoid
    stored-XSS from data already in the database.
  • Dashboard stats exposed to all authenticated users (filtered by role
    inside the query, not client-side).
"""

import html
from flask import Blueprint, jsonify, session
from app.db import get_db, dict_cursor
from app.decorators import login_required, admin_required

admin_bp = Blueprint("admin", __name__)


# ── Dashboard stats ───────────────────────────────────────────────────────

@admin_bp.route("/api/dashboard")
@login_required
def get_dashboard():
    db = get_db()
    cur = dict_cursor(db)
    try:
        stats = {}
        cur.execute("SELECT COUNT(*) AS total FROM espacio")
        stats["espacios"] = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS total FROM espacio WHERE estado = 'Disponible'")
        stats["espacios_disponibles"] = cur.fetchone()["total"]

        cur.execute("""
            SELECT COUNT(*) AS total FROM reserva
            WHERE fecha_reserva = CURDATE() AND estado_reserva = 'Activa'
        """)
        stats["reservas_hoy"] = cur.fetchone()["total"]

        cur.execute("""
            SELECT COUNT(*) AS total FROM reserva
            WHERE id_usuario = %s AND estado_reserva = 'Activa' AND fecha_reserva >= CURDATE()
        """, (session["user_id"],))
        stats["mis_reservas"] = cur.fetchone()["total"]

        if session.get("rol") == "Administrador":
            cur.execute("SELECT COUNT(*) AS total FROM usuario")
            stats["usuarios"] = cur.fetchone()["total"]
            cur.execute("""
                SELECT COUNT(*) AS total FROM mantenimiento
                WHERE estado_mantenimiento IN ('Programado', 'En Proceso')
            """)
            stats["mantenimientos_pendientes"] = cur.fetchone()["total"]

        return jsonify(stats)
    finally:
        cur.close()
        db.close()


# ── All reservations (admin table) ────────────────────────────────────────

@admin_bp.route("/api/admin/reservas/all")
@admin_required
def admin_reservas_all():
    db = get_db()
    cur = dict_cursor(db)
    try:
        cur.execute("""
            SELECT r.id_reserva, r.fecha_reserva, r.hora_inicio, r.hora_fin,
                   u.nombre AS usuario, e.nombre AS espacio_nombre
            FROM reserva r
            JOIN usuario u ON r.id_usuario = u.id_usuario
            JOIN espacio e ON r.id_espacio = e.id_espacio
            ORDER BY r.fecha_reserva DESC, r.hora_inicio ASC
        """)
        rows = cur.fetchall()
        for r in rows:
            r["hora_inicio"]   = str(r["hora_inicio"])
            r["hora_fin"]      = str(r["hora_fin"])
            r["fecha_reserva"] = str(r["fecha_reserva"])
        return jsonify(rows)
    finally:
        cur.close()
        db.close()


# ── Historial JSON ────────────────────────────────────────────────────────

@admin_bp.route("/api/historial")
@admin_required
def get_historial():
    db = get_db()
    cur = dict_cursor(db)
    try:
        cur.execute("""
            SELECT h.*, e.nombre AS espacio_nombre, u.nombre AS usuario_nombre
            FROM historial h
            JOIN espacio e ON h.id_espacio = e.id_espacio
            LEFT JOIN usuario u ON h.responsable_cambio = u.id_usuario
            ORDER BY h.fecha_cambio DESC
            LIMIT 100
        """)
        rows = cur.fetchall()
        for item in rows:
            if item.get("fecha_cambio"):
                item["fecha_cambio"] = str(item["fecha_cambio"])
        return jsonify(rows)
    finally:
        cur.close()
        db.close()


# ── Historial HTML view ───────────────────────────────────────────────────

@admin_bp.route("/api/historial/view")
@admin_required
def ver_historial():
    db = get_db()
    cur = dict_cursor(db)
    try:
        cur.execute("""
            SELECT h.id_historial, h.fecha_cambio, h.hora_cambio,
                   e.nombre AS espacio_nombre,
                   h.estado_anterior, h.estado_nuevo, h.responsable_cambio
            FROM historial h
            JOIN espacio e ON e.id_espacio = h.id_espacio
            ORDER BY h.fecha_cambio DESC, h.hora_cambio DESC
            LIMIT 300
        """)
        filas = cur.fetchall()
    finally:
        cur.close()
        db.close()

    # ── XSS mitigation: escape every cell from the DB ──
    def esc(v):
        return html.escape(str(v)) if v is not None else "-"

    filas_html = "".join(
        f"<tr>"
        f"<td>{esc(f['id_historial'])}</td>"
        f"<td>{esc(f['fecha_cambio'])} {esc(f.get('hora_cambio',''))}</td>"
        f"<td>{esc(f['espacio_nombre'])}</td>"
        f"<td>{esc(f['estado_anterior'])}</td>"
        f"<td>{esc(f['estado_nuevo'])}</td>"
        f"<td>{esc(f.get('responsable_cambio'))}</td>"
        f"</tr>"
        for f in filas
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Historial SGEC</title>
  <style>
    body{{font-family:system-ui;background:#071023;color:#e6f2ff;padding:20px}}
    table{{width:100%;border-collapse:collapse;background:#0f1b2b}}
    th,td{{border:1px solid #22344b;padding:8px;font-size:13px}}
    th{{background:#13233a}}
    tr:nth-child(even){{background:#101b30}}
  </style>
</head>
<body>
  <h1>Historial de cambios SGEC</h1>
  <table>
    <thead><tr><th>ID</th><th>Fecha/Hora</th><th>Espacio</th><th>Acción</th><th>Detalle</th><th>Responsable</th></tr></thead>
    <tbody>{filas_html or '<tr><td colspan="6">Sin registros</td></tr>'}</tbody>
  </table>
</body>
</html>"""


# ── Users list ────────────────────────────────────────────────────────────

@admin_bp.route("/api/usuarios")
@admin_required
def get_usuarios():
    db = get_db()
    cur = dict_cursor(db)
    try:
        cur.execute("""
            SELECT u.id_usuario, u.nombre, u.correo,
                   r.nombre_rol, u.fecha_creacion
            FROM usuario u
            JOIN rol r ON u.id_rol = r.id_rol
            ORDER BY u.fecha_creacion DESC
        """)
        rows = cur.fetchall()
        for u in rows:
            if u.get("fecha_creacion"):
                u["fecha_creacion"] = str(u["fecha_creacion"])
        return jsonify(rows)
    finally:
        cur.close()
        db.close()
