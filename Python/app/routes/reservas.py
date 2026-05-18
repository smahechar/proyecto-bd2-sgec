"""
app/routes/reservas.py
Reservation endpoints.

Security notes
──────────────
  • Dates and times validated with regex before reaching the DB.
  • Ownership check: users can only cancel their own reservations.
  • Admin can delete any reservation.
  • Parameterised stored procedure call — no raw SQL string injection.
"""

import mysql.connector
from flask import Blueprint, request, jsonify, session
from app.db import get_db, dict_cursor
from app.decorators import login_required, admin_required
from app.utils import (
    validate_date, validate_time,
    registrar_historial, registrar_auditoria_mongo,
    format_date, format_time,
)

reservas_bp = Blueprint("reservas", __name__, url_prefix="/api/reservas")


@reservas_bp.route("", methods=["GET"])
@login_required
def get_reservas():
    db = get_db()
    cur = dict_cursor(db)
    try:
        if session.get("rol") == "Administrador":
            cur.execute("""
                SELECT r.*, u.nombre AS usuario_nombre, e.nombre AS espacio_nombre
                FROM reserva r
                JOIN usuario u ON r.id_usuario = u.id_usuario
                JOIN espacio e ON r.id_espacio = e.id_espacio
                WHERE r.fecha_reserva >= CURDATE() - INTERVAL 7 DAY
                ORDER BY r.fecha_reserva DESC, r.hora_inicio DESC
                LIMIT 100
            """)
        else:
            cur.execute("""
                SELECT r.*, u.nombre AS usuario_nombre, e.nombre AS espacio_nombre
                FROM reserva r
                JOIN usuario u ON r.id_usuario = u.id_usuario
                JOIN espacio e ON r.id_espacio = e.id_espacio
                WHERE r.id_usuario = %s
                  AND r.fecha_reserva >= CURDATE() - INTERVAL 30 DAY
                ORDER BY r.fecha_reserva DESC, r.hora_inicio DESC
                LIMIT 50
            """, (session["user_id"],))

        rows = cur.fetchall()
        for r in rows:
            r["fecha_reserva"] = format_date(r["fecha_reserva"])
            r["hora_inicio"]   = format_time(r["hora_inicio"])
            r["hora_fin"]      = format_time(r["hora_fin"])
            if r.get("fecha_creacion"):
                r["fecha_creacion"] = str(r["fecha_creacion"])
        return jsonify(rows)
    finally:
        cur.close()
        db.close()


@reservas_bp.route("/proximas", methods=["GET"])
@login_required
def get_proximas():
    db = get_db()
    cur = dict_cursor(db)
    try:
        cur.execute("""
            SELECT r.*, e.nombre AS espacio_nombre
            FROM reserva r
            JOIN espacio e ON r.id_espacio = e.id_espacio
            WHERE r.id_usuario = %s
              AND r.estado_reserva = 'Activa'
              AND CONCAT(r.fecha_reserva, ' ', r.hora_inicio) >= NOW()
            ORDER BY r.fecha_reserva, r.hora_inicio
            LIMIT 5
        """, (session["user_id"],))
        rows = cur.fetchall()
        for r in rows:
            r["fecha_reserva"] = format_date(r["fecha_reserva"])
            r["hora_inicio"]   = format_time(r["hora_inicio"])
            r["hora_fin"]      = format_time(r["hora_fin"])
        return jsonify(rows)
    finally:
        cur.close()
        db.close()


@reservas_bp.route("", methods=["POST"])
@login_required
def crear_reserva():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "Cuerpo JSON requerido"}), 400

    try:
        id_espacio   = int(data.get("id_espacio", 0))
        fecha_reserva = validate_date(data.get("fecha_reserva", ""))
        hora_inicio   = validate_time(data.get("hora_inicio", ""))
        hora_fin      = validate_time(data.get("hora_fin", ""))
    except (ValueError, TypeError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    if id_espacio <= 0:
        return jsonify({"ok": False, "error": "ID de espacio inválido"}), 400
    if hora_fin <= hora_inicio:
        return jsonify({"ok": False, "error": "La hora fin debe ser mayor que la hora inicio"}), 400

    # Block students from creating reservations
    if session.get("rol") == "Estudiante":
        return jsonify({"ok": False, "error": "Los estudiantes no pueden crear reservas"}), 403

    db = get_db()
    cur  = db.cursor()
    cur2 = dict_cursor(db)

    try:
        # Check for active maintenance on that date
        cur.execute("""
            SELECT id_mantenimiento FROM mantenimiento
            WHERE id_espacio = %s AND fecha_inicio <= %s AND fecha_fin >= %s
            LIMIT 1
        """, (id_espacio, fecha_reserva, fecha_reserva))
        if cur.fetchone():
            return jsonify({"ok": False, "error": "El espacio está en mantenimiento en esta fecha."}), 400

        # Call stored procedure
        cur.callproc("crear_reserva", [session["user_id"], id_espacio, fecha_reserva, hora_inicio, hora_fin])

        registrar_historial(db, id_espacio, "Reserva",
                            f"Reserva {fecha_reserva} {hora_inicio}-{hora_fin}", session["user_id"])
        db.commit()

        registrar_auditoria_mongo(
            "RESERVA_CREATE", "Reservas",
            f"Espacio {id_espacio} reservado el {fecha_reserva}",
            usuario_id=session["user_id"],
            extra={"fecha": fecha_reserva, "inicio": hora_inicio, "fin": hora_fin},
        )
        return jsonify({"ok": True, "msg": "Reserva creada exitosamente"})

    except mysql.connector.Error as exc:
        db.rollback()
        msg = str(exc)
        if "Conflicto" in msg or "reservado" in msg:
            return jsonify({"ok": False, "error": "El espacio ya está reservado en ese horario"}), 409
        if "Hora fin" in msg:
            return jsonify({"ok": False, "error": "La hora de fin debe ser posterior a la de inicio"}), 400
        print(f"[RESERVAS] crear MySQL error: {exc}")
        return jsonify({"ok": False, "error": "Error al crear la reserva"}), 500
    finally:
        cur.close()
        cur2.close()
        db.close()


@reservas_bp.route("/<int:id_reserva>/cancelar", methods=["POST"])
@login_required
def cancelar_reserva(id_reserva):
    db = get_db()
    cur = dict_cursor(db)
    try:
        cur.execute("""
            SELECT r.*, e.nombre AS espacio_nombre
            FROM reserva r
            JOIN espacio e ON r.id_espacio = e.id_espacio
            WHERE r.id_reserva = %s LIMIT 1
        """, (id_reserva,))
        reserva = cur.fetchone()
        if not reserva:
            return jsonify({"ok": False, "error": "Reserva no encontrada"}), 404

        # Ownership check
        if reserva["id_usuario"] != session["user_id"] and session.get("rol") != "Administrador":
            return jsonify({"ok": False, "error": "No tienes permisos"}), 403

        cur.execute("UPDATE reserva SET estado_reserva = 'Cancelada' WHERE id_reserva = %s", (id_reserva,))
        registrar_historial(db, reserva["id_espacio"], "Cancelación",
                            f"Reserva #{id_reserva} cancelada", session["user_id"])
        cur.execute("INSERT INTO log_acciones (id_usuario, accion) VALUES (%s, %s)",
                    (session["user_id"], f"Canceló reserva #{id_reserva}"))
        db.commit()

        registrar_auditoria_mongo("RESERVA_CANCEL", "Reservas",
                                  f"Reserva #{id_reserva} cancelada", usuario_id=session["user_id"])
        return jsonify({"ok": True, "msg": "Reserva cancelada"})
    except Exception as exc:
        db.rollback()
        print(f"[RESERVAS] cancelar: {exc}")
        return jsonify({"ok": False, "error": "Error al cancelar"}), 500
    finally:
        cur.close()
        db.close()


@reservas_bp.route("/<int:id_reserva>", methods=["DELETE"])
@admin_required
def eliminar_reserva(id_reserva):
    db = get_db()
    cur = dict_cursor(db)
    try:
        cur.execute("SELECT id_espacio FROM reserva WHERE id_reserva = %s LIMIT 1", (id_reserva,))
        row = cur.fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Reserva no encontrada"}), 404

        cur.execute("DELETE FROM reserva WHERE id_reserva = %s", (id_reserva,))
        registrar_historial(db, row["id_espacio"], "Reserva eliminada",
                            f"Reserva #{id_reserva} eliminada por admin", session["user_id"])
        db.commit()

        registrar_auditoria_mongo("RESERVA_DELETE", "Reservas",
                                  f"Reserva #{id_reserva} eliminada", usuario_id=session["user_id"])
        return jsonify({"ok": True})
    except Exception as exc:
        db.rollback()
        print(f"[RESERVAS] eliminar: {exc}")
        return jsonify({"ok": False, "error": "Error interno"}), 500
    finally:
        cur.close()
        db.close()
