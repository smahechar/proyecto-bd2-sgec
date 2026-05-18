"""
app/routes/mantenimientos.py
Maintenance management endpoints (admin only).
"""

from flask import Blueprint, request, jsonify, session
from app.db import get_db, dict_cursor
from app.decorators import admin_required
from app.utils import (
    validate_date, validate_descripcion,
    registrar_historial, registrar_auditoria_mongo,
)

mant_bp = Blueprint("mantenimientos", __name__, url_prefix="/api/mantenimientos")


@mant_bp.route("", methods=["GET"])
@admin_required
def get_mantenimientos():
    db = get_db()
    cur = dict_cursor(db)
    try:
        cur.execute("""
            SELECT m.*, e.nombre AS espacio_nombre, u.nombre AS usuario_nombre
            FROM mantenimiento m
            JOIN espacio e ON m.id_espacio = e.id_espacio
            JOIN usuario u ON m.id_usuario = u.id_usuario
            ORDER BY m.fecha_creacion DESC
            LIMIT 50
        """)
        rows = cur.fetchall()
        for r in rows:
            if r.get("fecha_creacion"):
                r["fecha_creacion"] = str(r["fecha_creacion"])
        return jsonify(rows)
    finally:
        cur.close()
        db.close()


@mant_bp.route("/crear", methods=["POST"])
@admin_required
def crear_mantenimiento():
    data = request.get_json(silent=True) or {}

    try:
        id_espacio  = int(data.get("id_espacio", 0))
        fecha_inicio = validate_date(data.get("fecha_inicio", ""))
        fecha_fin    = validate_date(data.get("fecha_fin", ""))
        descripcion  = validate_descripcion(data.get("descripcion", ""))
    except (ValueError, TypeError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    if id_espacio <= 0:
        return jsonify({"ok": False, "error": "ID de espacio inválido"}), 400
    if fecha_fin < fecha_inicio:
        return jsonify({"ok": False, "error": "La fecha fin no puede ser anterior a la fecha inicio"}), 400

    db = get_db()
    cur = dict_cursor(db)
    try:
        cur.execute("""
            INSERT INTO mantenimiento
              (id_usuario, id_espacio, descripcion, estado_mantenimiento, fecha_inicio, fecha_fin)
            VALUES (%s, %s, %s, 'Programado', %s, %s)
        """, (session["user_id"], id_espacio, descripcion, fecha_inicio, fecha_fin))
        id_mant = cur.lastrowid

        # Mark space as under maintenance
        cur.execute("UPDATE espacio SET estado = 'Mantenimiento' WHERE id_espacio = %s", (id_espacio,))

        registrar_historial(db, id_espacio, "Mantenimiento",
                            f"Mantenimiento programado: {descripcion[:100]}", session["user_id"])
        db.commit()

        registrar_auditoria_mongo("MANT_CREATE", "Mantenimientos",
                                  f"Espacio {id_espacio}: {descripcion[:100]}",
                                  usuario_id=session["user_id"])
        return jsonify({"ok": True, "msg": "Mantenimiento programado", "id": id_mant})
    except Exception as exc:
        db.rollback()
        print(f"[MANT] crear: {exc}")
        return jsonify({"ok": False, "error": "Error al crear mantenimiento"}), 500
    finally:
        cur.close()
        db.close()


@mant_bp.route("/eliminar/<int:id_mantenimiento>", methods=["DELETE"])
@admin_required
def eliminar_mantenimiento(id_mantenimiento):
    db = get_db()
    cur = dict_cursor(db)
    try:
        cur.execute("SELECT * FROM mantenimiento WHERE id_mantenimiento = %s LIMIT 1", (id_mantenimiento,))
        mant = cur.fetchone()
        if not mant:
            return jsonify({"ok": False, "error": "Mantenimiento no encontrado"}), 404

        id_espacio = mant["id_espacio"]
        cur.execute("DELETE FROM mantenimiento WHERE id_mantenimiento = %s", (id_mantenimiento,))

        # If no other active maintenance, free the space
        cur.execute("""
            SELECT COUNT(*) AS total FROM mantenimiento
            WHERE id_espacio = %s AND estado_mantenimiento = 'Programado'
        """, (id_espacio,))
        if cur.fetchone()["total"] == 0:
            cur.execute("UPDATE espacio SET estado = 'Disponible' WHERE id_espacio = %s", (id_espacio,))

        db.commit()

        registrar_historial(db, id_espacio, "Mantenimiento eliminado",
                            f"Mantenimiento #{id_mantenimiento} eliminado", session["user_id"])
        registrar_auditoria_mongo("MANT_DELETE", "Mantenimientos",
                                  f"Eliminado #{id_mantenimiento}", usuario_id=session["user_id"])
        return jsonify({"ok": True})
    except Exception as exc:
        db.rollback()
        print(f"[MANT] eliminar: {exc}")
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        cur.close()
        db.close()
