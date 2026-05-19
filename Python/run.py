"""
SGEC - Sistema de Gestión de Espacios Colaborativos
Universidad El Bosque | Bases de Datos 2
Entry point — keeps this file minimal; real logic lives in app/
"""

from app import create_app
from app.routes.tailor import tailor_bp
print("tailor_bp url_prefix:", tailor_bp.url_prefix)

app = create_app()

if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║        Sistema de Gestión de Espacios (SGEC)          ║
    ║            Universidad El Bosque  — BD2               ║
    ╚═══════════════════════════════════════════════════════╝
     MySQL  → 192.168.56.102:13306
     MongoDB→ 192.168.56.101:27018
     Server → http://localhost:5000
    """)

    app.run(
        host="127.0.0.1",   # local only — use a proper WSGI server (gunicorn) in prod
        port=5000,
        debug=False          # NEVER run debug=True in production
    )
