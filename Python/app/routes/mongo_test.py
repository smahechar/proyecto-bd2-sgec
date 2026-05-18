"""
app/routes/mongo_test.py
Connectivity test route for the MongoDB integration.
Access: GET /api/test/mongo  (login required)
"""

from datetime import datetime
from flask import Blueprint, jsonify, session
from app.db import get_mongo
from app.decorators import login_required

mongo_bp = Blueprint("mongo_test", __name__)


@mongo_bp.route("/api/test/mongo")
@login_required
def test_mongo():
    try:
        mongo = get_mongo()
        mongo.audit_logs.insert_one({
            "accion":      "TEST_MONGO",
            "modulo":      "Conexion",
            "descripcion": "Prueba de conexión Flask → MongoDB",
            "usuario_id":  session.get("user_id"),
            "fecha":       datetime.utcnow(),
        })
        return jsonify({"ok": True, "msg": "MongoDB conectado correctamente"})
    except Exception as exc:
        print(f"[MONGO TEST] {exc}")
        return jsonify({"ok": False, "error": "No se pudo conectar a MongoDB"}), 500
