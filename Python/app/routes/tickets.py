from flask import Blueprint, jsonify, request, session
from app.db import get_db, dict_cursor
from app.decorators import login_required, admin_required
from app.utils import registrar_auditoria_mongo


tickets_bp = Blueprint("tickets", __name__, url_prefix="/api/tickets")


@tickets_bp.route("", methods=["GET"])
@login_required
def listar_tickets():
    db = get_db()
    cur = dict_cursor(db)

    try:
        if session.get("rol") == "Administrador":
            cur.execute("""
                SELECT 
                    t.*,
                    u.nombre AS docente_nombre,
                    c.nombre AS clase_nombre,
                    g.codigo_grupo,
                    e.nombre AS espacio_nombre
                FROM ticket_docente t
                JOIN usuario u ON u.id_usuario = t.id_usuario_docente
                LEFT JOIN grupo_clase g ON g.id_grupo_clase = t.id_grupo_clase
                LEFT JOIN clase c ON c.id_clase = g.id_clase
                LEFT JOIN espacio e ON e.id_espacio = t.id_espacio
                ORDER BY t.fecha_creacion DESC
            """)
        else:
            cur.execute("""
                SELECT 
                    t.*,
                    c.nombre AS clase_nombre,
                    g.codigo_grupo,
                    e.nombre AS espacio_nombre
                FROM ticket_docente t
                LEFT JOIN grupo_clase g ON g.id_grupo_clase = t.id_grupo_clase
                LEFT JOIN clase c ON c.id_clase = g.id_clase
                LEFT JOIN espacio e ON e.id_espacio = t.id_espacio
                WHERE t.id_usuario_docente = %s
                ORDER BY t.fecha_creacion DESC
            """, (session["user_id"],))

        rows = cur.fetchall()

        for row in rows:
            row["fecha_creacion"] = str(row["fecha_creacion"])
            row["fecha_actualizacion"] = str(row["fecha_actualizacion"])

        return jsonify({"ok": True, "tickets": rows})

    finally:
        cur.close()
        db.close()


@tickets_bp.route("", methods=["POST"])
@login_required
def crear_ticket():
    if session.get("rol") != "Docente":
        return jsonify({
            "ok": False,
            "error": "Solo los docentes pueden abrir tickets."
        }), 403

    data = request.get_json(silent=True) or {}

    asunto = (data.get("asunto") or "").strip()
    descripcion = (data.get("descripcion") or "").strip()
    id_grupo_clase = data.get("id_grupo_clase")
    id_espacio = data.get("id_espacio")

    if len(asunto) < 3 or len(descripcion) < 5:
        return jsonify({
            "ok": False,
            "error": "Asunto o descripción demasiado cortos."
        }), 400

    db = get_db()
    cur = dict_cursor(db)

    try:
        cur.execute("""
            INSERT INTO ticket_docente (
                id_usuario_docente,
                id_grupo_clase,
                id_espacio,
                asunto,
                descripcion
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            session["user_id"],
            id_grupo_clase,
            id_espacio,
            asunto,
            descripcion
        ))

        id_ticket = cur.lastrowid
        db.commit()

        registrar_auditoria_mongo(
            "TICKET_CREATE",
            "Tickets",
            f"Docente abrió ticket: {asunto}",
            usuario_id=session.get("user_id"),
            extra={
                "id_ticket": id_ticket,
                "id_grupo_clase": id_grupo_clase,
                "id_espacio": id_espacio
            }
        )

        return jsonify({
            "ok": True,
            "msg": "Ticket creado correctamente.",
            "id_ticket": id_ticket
        })

    except Exception as exc:
        db.rollback()
        print(f"[TICKETS] crear: {exc}")
        return jsonify({"ok": False, "error": "Error creando ticket"}), 500

    finally:
        cur.close()
        db.close()


@tickets_bp.route("/<int:id_ticket>/estado", methods=["PUT", "POST"])
@admin_required
def actualizar_ticket(id_ticket):
    data = request.get_json(silent=True) or {}

    estado = data.get("estado", "En revisión")
    respuesta = data.get("respuesta_admin", "")

    if estado not in ["Abierto", "En revisión", "Resuelto", "Cerrado"]:
        return jsonify({"ok": False, "error": "Estado inválido"}), 400

    db = get_db()
    cur = dict_cursor(db)

    try:
        cur.execute("""
            UPDATE ticket_docente
            SET estado = %s,
                respuesta_admin = %s
            WHERE id_ticket = %s
        """, (estado, respuesta, id_ticket))

        db.commit()

        registrar_auditoria_mongo(
            "TICKET_UPDATE",
            "Tickets",
            f"Administrador actualizó ticket #{id_ticket} a {estado}",
            usuario_id=session.get("user_id"),
            extra={
                "id_ticket": id_ticket,
                "estado": estado,
                "respuesta_admin": respuesta
            }
        )

        return jsonify({"ok": True, "msg": "Ticket actualizado."})

    except Exception as exc:
        db.rollback()
        print(f"[TICKETS] actualizar: {exc}")
        return jsonify({"ok": False, "error": "Error actualizando ticket"}), 500

    finally:
        cur.close()
        db.close()