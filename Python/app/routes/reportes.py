"""
app/routes/reportes.py
CSV export endpoints.

Security notes
──────────────
  • All exports require authentication (historial also requires admin).
  • Content-Disposition header set so browser prompts download — not render.
  • No user-controlled data injected into the filename.
"""

import csv
import io
from flask import Blueprint, Response, jsonify
from app.db import get_db, dict_cursor
from app.decorators import login_required, admin_required

reportes_bp = Blueprint("reportes", __name__, url_prefix="/api/reportes")


def _csv_response(rows: list[dict], headers: list[str], filename: str, row_fn) -> Response:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for r in rows:
        writer.writerow(row_fn(r))
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@reportes_bp.route("/historial")
@admin_required
def exportar_historial():
    db = get_db()
    cur = dict_cursor(db)
    try:
        cur.execute("""
            SELECT h.id_historial, e.nombre AS nombre_espacio,
                   h.estado_anterior, h.estado_nuevo,
                   h.fecha_cambio, h.hora_cambio,
                   h.fecha_creacion, h.fecha_modificacion,
                   u.nombre AS responsable
            FROM historial h
            LEFT JOIN espacio e ON h.id_espacio = e.id_espacio
            LEFT JOIN usuario u ON h.responsable_cambio = u.id_usuario
            ORDER BY h.fecha_cambio DESC
        """)
        rows = cur.fetchall()
    finally:
        cur.close()
        db.close()

    return _csv_response(
        rows,
        headers=["ID", "Espacio", "Acción", "Detalle", "Fecha", "Hora", "Registrado", "Actualizado", "Responsable"],
        filename="reporte_historial.csv",
        row_fn=lambda r: [
            r["id_historial"], r["nombre_espacio"], r["estado_anterior"],
            r["estado_nuevo"], r["fecha_cambio"], r["hora_cambio"],
            r["fecha_creacion"], r["fecha_modificacion"], r["responsable"],
        ],
    )


@reportes_bp.route("/reservas")
@login_required
def exportar_reservas():
    db = get_db()
    cur = dict_cursor(db)
    try:
        cur.execute("""
            SELECT r.id_reserva, u.nombre AS usuario, e.nombre AS espacio,
                   r.fecha_reserva, r.hora_inicio, r.hora_fin, r.estado_reserva
            FROM reserva r
            JOIN usuario u ON u.id_usuario = r.id_usuario
            JOIN espacio e ON e.id_espacio = r.id_espacio
            ORDER BY r.fecha_reserva DESC, r.hora_inicio
        """)
        rows = cur.fetchall()
    except Exception as exc:
        print(f"[REPORTES] reservas: {exc}")
        return jsonify({"ok": False, "error": "Error generando reporte"}), 500
    finally:
        cur.close()
        db.close()

    return _csv_response(
        rows,
        headers=["ID", "Usuario", "Espacio", "Fecha", "Hora Inicio", "Hora Fin", "Estado"],
        filename="reporte_reservas.csv",
        row_fn=lambda r: [
            r["id_reserva"], r["usuario"], r["espacio"],
            r["fecha_reserva"], r["hora_inicio"], r["hora_fin"], r["estado_reserva"],
        ],
    )
