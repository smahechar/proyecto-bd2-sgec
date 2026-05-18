"""
app/routes/espacios.py
Space (espacio) CRUD endpoints.

Security notes
──────────────
  • All inputs validated and size-capped before touching the DB.
  • estado is whitelisted to a known set of values.
  • Parameterised queries throughout — no f-string SQL.
  • Only admin can create / edit / delete spaces.
"""

from flask import Blueprint, request, jsonify, session
from app.db import get_db, dict_cursor
from app.decorators import login_required, admin_required
from app.utils import (
    validate_nombre, validate_estado, validate_descripcion,
    validate_capacidad, registrar_historial, registrar_auditoria_mongo,
)

espacios_bp = Blueprint("espacios", __name__, url_prefix="/api/espacios")


@espacios_bp.route("")
@login_required
def get_espacios():
    db = get_db()
    cur = dict_cursor(db)
    try:
        cur.execute("""
            SELECT id_espacio, nombre, estado,
                   COALESCE(capacidad, 0)    AS capacidad,
                   COALESCE(descripcion, '') AS descripcion,
                   fecha_modificacion
            FROM espacio
            ORDER BY nombre
        """)
        rows = cur.fetchall()
        for r in rows:
            if r.get("fecha_modificacion"):
                r["fecha_modificacion"] = str(r["fecha_modificacion"])
        return jsonify(rows)
    finally:
        cur.close()
        db.close()


@espacios_bp.route("/<int:id_espacio>")
@login_required
def get_espacio(id_espacio):
    db = get_db()
    cur = dict_cursor(db)
    try:
        cur.execute("SELECT * FROM espacio WHERE id_espacio = %s LIMIT 1", (id_espacio,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Espacio no encontrado"}), 404
        if row.get("fecha_modificacion"):
            row["fecha_modificacion"] = str(row["fecha_modificacion"])
        return jsonify(row)
    finally:
        cur.close()
        db.close()


@espacios_bp.route("/crear", methods=["POST"])
@admin_required
def crear_espacio():
    data = request.get_json(silent=True) or request.form

    try:
        nombre     = validate_nombre(data.get("nombre", ""))
        estado     = validate_estado(data.get("estado", "Disponible"))
        capacidad  = validate_capacidad(data.get("capacidad", 0))
        descripcion = validate_descripcion(data.get("descripcion", ""))
    except ValueError as e:
        return jsonify({"ok": False, "msg": str(e)}), 400

    db = get_db()
    cur = dict_cursor(db)
    try:
        cur.execute(
            "INSERT INTO espacio (nombre, estado, capacidad, descripcion) VALUES (%s,%s,%s,%s)",
            (nombre, estado, capacidad, descripcion),
        )
        id_espacio = cur.lastrowid
        registrar_historial(db, id_espacio, "Creación", f"Espacio '{nombre}' creado", session["user_id"])
        db.commit()
        registrar_auditoria_mongo("ESPACIO_CREATE", "Espacios", f"Creado: {nombre}", usuario_id=session["user_id"])
        return jsonify({"ok": True, "msg": "Espacio creado", "id": id_espacio})
    except Exception as exc:
        db.rollback()
        print(f"[ESPACIOS] crear: {exc}")
        return jsonify({"ok": False, "msg": "Error al crear espacio"}), 500
    finally:
        cur.close()
        db.close()


@espacios_bp.route("/<int:id_espacio>/editar", methods=["PUT", "POST"])
@admin_required
def editar_espacio(id_espacio):
    data = request.get_json(silent=True) or request.form

    updates, params, cambios = [], [], []

    try:
        if "nombre" in data:
            nombre = validate_nombre(data["nombre"])
            updates.append("nombre = %s"); params.append(nombre)
            cambios.append(f"Nombre → '{nombre}'")
        if "estado" in data:
            estado = validate_estado(data["estado"])
            updates.append("estado = %s"); params.append(estado)
            cambios.append(f"Estado → '{estado}'")
        if "capacidad" in data:
            cap = validate_capacidad(data["capacidad"])
            updates.append("capacidad = %s"); params.append(cap)
            cambios.append(f"Capacidad → {cap}")
        if "descripcion" in data:
            desc = validate_descripcion(data["descripcion"])
            updates.append("descripcion = %s"); params.append(desc)
    except ValueError as e:
        return jsonify({"ok": False, "msg": str(e)}), 400

    if not updates:
        return jsonify({"ok": False, "msg": "No hay cambios para aplicar"}), 400

    db = get_db()
    cur = dict_cursor(db)
    try:
        cur.execute("SELECT id_espacio FROM espacio WHERE id_espacio = %s", (id_espacio,))
        if not cur.fetchone():
            return jsonify({"ok": False, "msg": "Espacio no encontrado"}), 404

        params.append(id_espacio)
        cur.execute(f"UPDATE espacio SET {', '.join(updates)} WHERE id_espacio = %s", params)

        if cambios:
            registrar_historial(db, id_espacio, "Modificación", "; ".join(cambios), session["user_id"])

        db.commit()
        registrar_auditoria_mongo("ESPACIO_EDIT", "Espacios", "; ".join(cambios), usuario_id=session["user_id"])
        return jsonify({"ok": True, "msg": "Espacio actualizado"})
    except Exception as exc:
        db.rollback()
        print(f"[ESPACIOS] editar: {exc}")
        return jsonify({"ok": False, "msg": "Error al actualizar"}), 500
    finally:
        cur.close()
        db.close()


@espacios_bp.route("/<int:id_espacio>/eliminar", methods=["DELETE", "POST"])
@admin_required
def eliminar_espacio(id_espacio):
    db = get_db()
    cur = dict_cursor(db)
    try:
        cur.execute("SELECT nombre FROM espacio WHERE id_espacio = %s", (id_espacio,))
        espacio = cur.fetchone()
        if not espacio:
            return jsonify({"ok": False, "msg": "Espacio no encontrado"}), 404

        cur.execute("""
            SELECT COUNT(*) AS total FROM reserva
            WHERE id_espacio = %s AND estado_reserva = 'Activa' AND fecha_reserva >= CURDATE()
        """, (id_espacio,))
        if cur.fetchone()["total"] > 0:
            return jsonify({"ok": False, "msg": "No se puede eliminar: tiene reservas activas"}), 400

        registrar_historial(db, id_espacio, "Eliminación", f"Espacio '{espacio['nombre']}' eliminado", session["user_id"])
        cur.execute("DELETE FROM espacio WHERE id_espacio = %s", (id_espacio,))
        db.commit()
        registrar_auditoria_mongo("ESPACIO_DELETE", "Espacios", f"Eliminado: {espacio['nombre']}", usuario_id=session["user_id"])
        return jsonify({"ok": True, "msg": "Espacio eliminado"})
    except Exception as exc:
        db.rollback()
        print(f"[ESPACIOS] eliminar: {exc}")
        return jsonify({"ok": False, "msg": "Error al eliminar"}), 500
    finally:
        cur.close()
        db.close()
