from datetime import datetime, timedelta
from flask import Blueprint, jsonify, Response, render_template_string
from app.db import get_mongo
from app.decorators import admin_required
import csv
import io
import html


mongo_reports_bp = Blueprint("mongo_reports", __name__, url_prefix="/api/mongo")


def _serialize_doc(doc):
    """Convierte ObjectId y datetime a string para responder JSON."""
    doc["_id"] = str(doc.get("_id"))
    for key, value in list(doc.items()):
        if isinstance(value, datetime):
            doc[key] = value.isoformat()
    return doc


@mongo_reports_bp.route("/dashboard")
@admin_required
def mongo_dashboard():
    """
    Estadísticas generales desde MongoDB:
    auditorías, eventos de asignación, eventos de seguridad y estadísticas.
    """
    try:
        mongo = get_mongo()

        total_auditorias = mongo.audit_logs.count_documents({})
        total_asignaciones = mongo.eventos_asignacion.count_documents({})
        total_seguridad = mongo.eventos_seguridad.count_documents({})
        total_estadisticas = mongo.estadisticas.count_documents({})

        acciones = list(mongo.audit_logs.aggregate([
            {"$group": {"_id": "$accion", "total": {"$sum": 1}}},
            {"$sort": {"total": -1}},
            {"$limit": 10}
        ]))

        modulos = list(mongo.audit_logs.aggregate([
            {"$group": {"_id": "$modulo", "total": {"$sum": 1}}},
            {"$sort": {"total": -1}},
            {"$limit": 10}
        ]))

        ultimos_eventos = list(
            mongo.audit_logs.find({})
            .sort("fecha", -1)
            .limit(10)
        )

        return jsonify({
            "ok": True,
            "resumen": {
                "total_auditorias": total_auditorias,
                "total_eventos_asignacion": total_asignaciones,
                "total_eventos_seguridad": total_seguridad,
                "total_estadisticas": total_estadisticas
            },
            "acciones_mas_frecuentes": [
                {"accion": item["_id"], "total": item["total"]}
                for item in acciones
            ],
            "modulos_mas_frecuentes": [
                {"modulo": item["_id"], "total": item["total"]}
                for item in modulos
            ],
            "ultimos_eventos": [_serialize_doc(doc) for doc in ultimos_eventos]
        })

    except Exception as exc:
        print(f"[MONGO REPORTS] dashboard: {exc}")
        return jsonify({
            "ok": False,
            "error": "No se pudieron generar las estadísticas MongoDB"
        }), 500


@mongo_reports_bp.route("/auditorias")
@admin_required
def mongo_auditorias():
    """
    Informe de auditorías desde audit_logs.
    """
    try:
        mongo = get_mongo()
        docs = list(
            mongo.audit_logs.find({})
            .sort("fecha", -1)
            .limit(200)
        )

        return jsonify({
            "ok": True,
            "total_mostrado": len(docs),
            "auditorias": [_serialize_doc(doc) for doc in docs]
        })

    except Exception as exc:
        print(f"[MONGO REPORTS] auditorias: {exc}")
        return jsonify({
            "ok": False,
            "error": "No se pudo consultar el informe de auditorías"
        }), 500


@mongo_reports_bp.route("/mantenimientos")
@admin_required
def mongo_mantenimientos():
    """
    Registro de mantenimientos desde MongoDB.
    Busca eventos MANT_CREATE y MANT_DELETE en audit_logs.
    """
    try:
        mongo = get_mongo()
        docs = list(
            mongo.audit_logs.find({
                "accion": {"$in": ["MANT_CREATE", "MANT_DELETE"]}
            })
            .sort("fecha", -1)
            .limit(200)
        )

        return jsonify({
            "ok": True,
            "total_mostrado": len(docs),
            "mantenimientos": [_serialize_doc(doc) for doc in docs]
        })

    except Exception as exc:
        print(f"[MONGO REPORTS] mantenimientos: {exc}")
        return jsonify({
            "ok": False,
            "error": "No se pudo consultar el registro de mantenimientos"
        }), 500


@mongo_reports_bp.route("/seguridad")
@admin_required
def mongo_seguridad():
    """
    Eventos de seguridad desde MongoDB.
    Combina eventos_seguridad y auditorías LOGIN_FAIL / LOGIN_OK.
    """
    try:
        mongo = get_mongo()

        eventos_seguridad = list(
            mongo.eventos_seguridad.find({})
            .sort("fecha", -1)
            .limit(100)
        )

        login_events = list(
            mongo.audit_logs.find({
                "accion": {"$in": ["LOGIN_OK", "LOGIN_FAIL", "LOGOUT", "REGISTER"]}
            })
            .sort("fecha", -1)
            .limit(100)
        )

        return jsonify({
            "ok": True,
            "eventos_seguridad": [_serialize_doc(doc) for doc in eventos_seguridad],
            "eventos_login": [_serialize_doc(doc) for doc in login_events]
        })

    except Exception as exc:
        print(f"[MONGO REPORTS] seguridad: {exc}")
        return jsonify({
            "ok": False,
            "error": "No se pudieron consultar los eventos de seguridad"
        }), 500


@mongo_reports_bp.route("/asignaciones")
@admin_required
def mongo_asignaciones():
    """
    Eventos de asignación tailor made desde MongoDB.
    """
    try:
        mongo = get_mongo()
        docs = list(
            mongo.eventos_asignacion.find({})
            .sort("fecha", -1)
            .limit(200)
        )

        return jsonify({
            "ok": True,
            "total_mostrado": len(docs),
            "asignaciones": [_serialize_doc(doc) for doc in docs]
        })

    except Exception as exc:
        print(f"[MONGO REPORTS] asignaciones: {exc}")
        return jsonify({
            "ok": False,
            "error": "No se pudieron consultar los eventos de asignación"
        }), 500


@mongo_reports_bp.route("/auditorias/csv")
@admin_required
def mongo_auditorias_csv():
    """
    Exporta audit_logs como CSV.
    """
    try:
        mongo = get_mongo()
        docs = list(
            mongo.audit_logs.find({})
            .sort("fecha", -1)
            .limit(1000)
        )

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "ID",
            "Fecha",
            "Accion",
            "Modulo",
            "Usuario ID",
            "IP",
            "Descripcion",
            "Extra"
        ])

        for doc in docs:
            writer.writerow([
                str(doc.get("_id", "")),
                doc.get("fecha", ""),
                doc.get("accion", ""),
                doc.get("modulo", ""),
                doc.get("usuario_id", ""),
                doc.get("ip", ""),
                doc.get("descripcion", ""),
                str(doc.get("extra", {}))
            ])

        csv_content = "\ufeff" + output.getvalue()

        return Response(
            csv_content,
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": "attachment; filename=reporte_auditorias_mongo.csv"
            }
        )

    except Exception as exc:
        print(f"[MONGO REPORTS] auditorias csv: {exc}")
        return jsonify({
            "ok": False,
            "error": "No se pudo exportar auditorías MongoDB"
        }), 500

def _esc(value):
    if value is None:
        return "-"
    return html.escape(str(value))


def _mongo_page(title, subtitle, headers, rows_html):
    return render_template_string(f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>{_esc(title)}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: #071023;
                color: #e6f2ff;
                padding: 24px;
            }}

            h1 {{
                color: #00e6b8;
                margin-bottom: 6px;
            }}

            p {{
                color: #a8bfd8;
            }}

            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
                background: #0f1b2b;
                border-radius: 12px;
                overflow: hidden;
            }}

            th, td {{
                border: 1px solid #22344b;
                padding: 10px;
                font-size: 13px;
                vertical-align: top;
            }}

            th {{
                background: #13233a;
                color: #00e6b8;
                text-align: left;
            }}

            tr:nth-child(even) {{
                background: #101b30;
            }}

            pre {{
                white-space: pre-wrap;
                word-break: break-word;
                margin: 0;
                font-family: Consolas, monospace;
                font-size: 12px;
                color: #d9f7ff;
            }}

            .btn {{
                display: inline-block;
                margin-bottom: 16px;
                background: linear-gradient(135deg, #00c6ff, #00e6b8);
                color: #071023;
                padding: 10px 14px;
                border-radius: 10px;
                text-decoration: none;
                font-weight: bold;
            }}
        </style>
    </head>
    <body>
        <a class="btn" href="/home">← Volver al sistema</a>
        <h1>{_esc(title)}</h1>
        <p>{_esc(subtitle)}</p>

        <table>
            <thead>
                <tr>
                    {''.join(f'<th>{_esc(h)}</th>' for h in headers)}
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </body>
    </html>
    """)


@mongo_reports_bp.route("/auditorias/view")
@admin_required
def mongo_auditorias_view():
    try:
        mongo = get_mongo()
        docs = list(
            mongo.audit_logs.find({})
            .sort("fecha", -1)
            .limit(200)
        )

        rows = ""
        for doc in docs:
            rows += f"""
            <tr>
                <td>{_esc(doc.get("fecha"))}</td>
                <td>{_esc(doc.get("accion"))}</td>
                <td>{_esc(doc.get("modulo"))}</td>
                <td>{_esc(doc.get("usuario_id"))}</td>
                <td>{_esc(doc.get("ip"))}</td>
                <td>{_esc(doc.get("descripcion"))}</td>
                <td><pre>{_esc(doc.get("extra", {}))}</pre></td>
            </tr>
            """

        if not rows:
            rows = '<tr><td colspan="7">No hay auditorías para mostrar.</td></tr>'

        return _mongo_page(
            "Informe de Auditorías MongoDB",
            "Registros consultados desde la colección audit_logs.",
            ["Fecha", "Acción", "Módulo", "Usuario", "IP", "Descripción", "Detalle"],
            rows
        )

    except Exception as exc:
        print(f"[MONGO VIEW] auditorias: {exc}")
        return "Error consultando auditorías MongoDB", 500


@mongo_reports_bp.route("/asignaciones/view")
@admin_required
def mongo_asignaciones_view():
    try:
        mongo = get_mongo()
        docs = list(
            mongo.eventos_asignacion.find({})
            .sort("fecha", -1)
            .limit(200)
        )

        rows = ""
        for doc in docs:
            detalle = doc.get("detalle", {})

            rows += f"""
            <tr>
                <td>{_esc(doc.get("fecha"))}</td>
                <td>{_esc(detalle.get("clase"))}</td>
                <td>{_esc(detalle.get("grupo"))}</td>
                <td>{_esc(detalle.get("cantidad_estudiantes"))}</td>
                <td>{_esc(detalle.get("salon_codigo"))}</td>
                <td>{_esc(detalle.get("capacidad_salon"))}</td>
                <td>{_esc(detalle.get("diferencia_capacidad"))}</td>
                <td>{_esc(detalle.get("criterio"))}</td>
            </tr>
            """

        if not rows:
            rows = '<tr><td colspan="8">No hay asignaciones para mostrar.</td></tr>'

        return _mongo_page(
            "Eventos de Asignación Tailor Made",
            "Asignaciones automáticas consultadas desde MongoDB.",
            ["Fecha", "Clase", "Grupo", "Estudiantes", "Salón", "Capacidad", "Diferencia", "Criterio"],
            rows
        )

    except Exception as exc:
        print(f"[MONGO VIEW] asignaciones: {exc}")
        return "Error consultando asignaciones MongoDB", 500


@mongo_reports_bp.route("/seguridad/view")
@admin_required
def mongo_seguridad_view():
    try:
        mongo = get_mongo()
        docs = list(
            mongo.audit_logs.find({
                "accion": {"$in": ["LOGIN_OK", "LOGIN_FAIL", "LOGOUT", "REGISTER"]}
            })
            .sort("fecha", -1)
            .limit(200)
        )

        rows = ""
        for doc in docs:
            rows += f"""
            <tr>
                <td>{_esc(doc.get("fecha"))}</td>
                <td>{_esc(doc.get("accion"))}</td>
                <td>{_esc(doc.get("usuario_id"))}</td>
                <td>{_esc(doc.get("ip"))}</td>
                <td>{_esc(doc.get("descripcion"))}</td>
            </tr>
            """

        if not rows:
            rows = '<tr><td colspan="5">No hay eventos de seguridad para mostrar.</td></tr>'

        return _mongo_page(
            "Eventos de Seguridad MongoDB",
            "Accesos, cierres de sesión, registros e intentos fallidos.",
            ["Fecha", "Acción", "Usuario", "IP", "Descripción"],
            rows
        )

    except Exception as exc:
        print(f"[MONGO VIEW] seguridad: {exc}")
        return "Error consultando seguridad MongoDB", 500