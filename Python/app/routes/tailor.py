"""
app/routes/tailor.py

Tailor-made semester assignment module.

Fixes applied (vs previous version):
  - INSERT INTO reserva uses an explicit SELECT + conditional INSERT instead of
    INSERT ... SELECT ... WHERE NOT EXISTS (which silently inserts 0 rows in MySQL
    when the subquery returns a row, with no error raised).
  - reserva rows now include `origen = 'SEMESTRAL'` and `id_horario` columns.
    Run the ALTER statements below in MySQL before deploying this file.
  - Per-group and total counters for reservas_creadas / reservas_conflicto are
    tracked and returned in the JSON response.
  - Debug prints added so you can watch the server log during testing.
  - Old SEMESTRAL reservas and horario_semestre rows are cleaned before
    re-running the algorithm.

Required MySQL migration (run once):
  ALTER TABLE reserva ADD COLUMN IF NOT EXISTS origen   VARCHAR(30) DEFAULT 'MANUAL';
  ALTER TABLE reserva ADD COLUMN IF NOT EXISTS id_horario INT NULL;
"""

from datetime import datetime, timedelta, date
import random

from flask import Blueprint, jsonify, request, session
from app.db import get_db, dict_cursor
from app.decorators import admin_required, login_required
from app.utils import registrar_auditoria_mongo


tailor_bp = Blueprint("tailor", __name__, url_prefix="/api/tailor")


DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]

BLOQUES_HORARIOS = [
    ("07:00", "09:00"),
    ("09:00", "11:00"),
    ("11:00", "13:00"),
    ("14:00", "16:00"),
    ("16:00", "18:00"),
    ("18:00", "20:00"),
    ("20:00", "22:00"),
]

SLOTS_SEMANALES = [
    (dia, hora_inicio, hora_fin)
    for dia in DIAS
    for hora_inicio, hora_fin in BLOQUES_HORARIOS
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _next_weekday(start_date: date, dia_semana: str) -> date:
    dias_map = {
        "Lunes": 0,
        "Martes": 1,
        "Miércoles": 2,
        "Jueves": 3,
        "Viernes": 4,
        "Sábado": 5,
    }
    target = dias_map[dia_semana]
    diff = (target - start_date.weekday()) % 7
    return start_date + timedelta(days=diff)


def _fechas_recurrentes(fecha_inicio: date, fecha_fin: date, dia_semana: str) -> list:
    actual = _next_weekday(fecha_inicio, dia_semana)
    fechas = []
    while actual <= fecha_fin:
        fechas.append(actual)
        actual += timedelta(days=7)
    return fechas


def _time_conflict(hi_new, hf_new, hi_row, hf_row) -> bool:
    """True if two time intervals overlap (all values are strings 'HH:MM')."""
    return hi_new < hf_row and hf_new > hi_row

def generar_cantidad_estudiantes():
    """
    Genera cantidades de estudiantes con distribución más realista.

    La mayoría de grupos quedan por debajo de 40 estudiantes.
    Solo unos pocos grupos son grandes.
    """
    probabilidad = random.random()

    if probabilidad < 0.80:
        # 80% de grupos pequeños/medianos
        return random.randint(18, 34)

    elif probabilidad < 0.95:
        # 15% de grupos cerca del límite de salón estándar
        return random.randint(35, 40)

    elif probabilidad < 0.99:
        # 4% de grupos grandes
        return random.randint(41, 50)

    else:
        # 1% de grupos muy grandes
        return random.randint(51, 65)
# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@tailor_bp.route("/generar-cupos", methods=["POST"])
@admin_required
def generar_cupos_aleatorios():
    """
    Genera cantidades aleatorias de estudiantes por grupo.
    Simula la demanda real de matrícula de cada grupo.
    """
    data = request.get_json(silent=True) or {}

    minimo = int(data.get("minimo", 18))
    maximo = int(data.get("maximo", 70))

    if minimo < 1 or maximo > 100 or minimo > maximo:
        return jsonify({
            "ok": False,
            "error": "Rango inválido. Usa mínimo >= 1, máximo <= 100 y mínimo <= máximo."
        }), 400

    db  = get_db()
    cur = dict_cursor(db)

    try:
        cur.execute("SELECT id_grupo_clase FROM grupo_clase WHERE estado = 'Activo'")
        grupos = cur.fetchall()
        total = 0

        for grupo in grupos:
            cantidad = generar_cantidad_estudiantes()
            cur.execute(
                "UPDATE grupo_clase SET cantidad_estudiantes = %s WHERE id_grupo_clase = %s",
                (cantidad, grupo["id_grupo_clase"])
            )
            total += 1

        db.commit()

        registrar_auditoria_mongo(
            "GENERAR_CUPOS_ALEATORIOS",
            "TailorMade",
            f"Se generaron cupos aleatorios para {total} grupos.",
            usuario_id=session.get("user_id"),
            extra={
                "distribucion": "70% entre 18-35, 20% entre 36-40, 7% entre 41-55, 3% entre 56-70",
                "total_grupos": total
            }
        )

        return jsonify({
            "ok": True,
            "msg": f"Cupos aleatorios generados para {total} grupos.",
            "total_grupos": total
        })

    except Exception as exc:
        db.rollback()
        print(f"[TAILOR] generar_cupos error: {exc}")
        return jsonify({"ok": False, "error": "Error generando cupos aleatorios"}), 500

    finally:
        cur.close()
        db.close()


@tailor_bp.route("/asignar-semestre", methods=["POST"])
@admin_required
def asignar_semestre():
    """
    Asigna salones automáticamente para todo el semestre.

    Guarda:
      - Horario fijo en horario_semestre.
      - Una reserva por cada ocurrencia semanal en la tabla reserva
        (con origen='SEMESTRAL' e id_horario para trazabilidad).
      - Auditoría en MongoDB.

    Retorna un JSON con contadores de asignaciones y reservas creadas.
    """
    data = request.get_json(silent=True) or {}

    fecha_inicio_str = data.get("fecha_inicio")
    fecha_fin_str    = data.get("fecha_fin")

    if not fecha_inicio_str or not fecha_fin_str:
        return jsonify({
            "ok": False,
            "error": "Debes enviar fecha_inicio y fecha_fin."
        }), 400

    try:
        fecha_inicio = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
        fecha_fin    = datetime.strptime(fecha_fin_str,    "%Y-%m-%d").date()
    except ValueError:
        return jsonify({
            "ok": False,
            "error": "Formato de fecha inválido. Usa YYYY-MM-DD."
        }), 400

    if fecha_fin <= fecha_inicio:
        return jsonify({
            "ok": False,
            "error": "La fecha fin debe ser mayor a la fecha inicio."
        }), 400

    db  = get_db()
    cur = dict_cursor(db)

    asignadas = []
    rechazadas = []
    total_reservas_creadas   = 0
    total_reservas_conflicto = 0

    try:
        # ── 1. Limpiar asignaciones y reservas semestrales previas ──────────
        cur.execute("DELETE FROM reserva WHERE origen = 'SEMESTRAL'")
        deleted_reservas = cur.rowcount
        print(f"[TAILOR] Reservas SEMESTRAL eliminadas: {deleted_reservas}")

        cur.execute("DELETE FROM horario_semestre WHERE estado = 'Activo'")
        deleted_horarios = cur.rowcount
        print(f"[TAILOR] Horarios eliminados: {deleted_horarios}")

        # ── 2. Cargar grupos activos ─────────────────────────────────────────
        cur.execute("""
            SELECT
                g.id_grupo_clase,
                g.codigo_grupo,
                g.cantidad_estudiantes,
                c.id_clase,
                c.nombre          AS clase_nombre,
                c.tipo_clase,
                c.requiere_computadores,
                c.requiere_laboratorio,
                c.especialidad_requerida
            FROM grupo_clase g
            JOIN clase c ON c.id_clase = g.id_clase
            WHERE g.estado = 'Activo'
            ORDER BY g.cantidad_estudiantes DESC, g.id_grupo_clase ASC
        """)
        grupos = cur.fetchall()
        print(f"[TAILOR] Grupos activos encontrados: {len(grupos)}")

        # ── 3. Procesar cada grupo ───────────────────────────────────────────
        for idx, grupo in enumerate(grupos):
            cantidad = int(grupo["cantidad_estudiantes"] or generar_cantidad_estudiantes())

            # Cada grupo inicia en un slot diferente, pero puede probar todos los slots
            slot_inicial = idx % len(SLOTS_SEMANALES)
            slots_a_probar = SLOTS_SEMANALES[slot_inicial:] + SLOTS_SEMANALES[:slot_inicial]

            espacio = None
            slot_elegido = None

            # Buscar docente asignado al grupo
            cur.execute("""
                SELECT id_usuario
                FROM docente_grupo_clase
                WHERE id_grupo_clase = %s AND estado = 'Activo'
                LIMIT 1
            """, (grupo["id_grupo_clase"],))

            docente = cur.fetchone()
            id_docente = docente["id_usuario"] if docente else None

            # Buscar salón más ajustado probando toda la semana
            for dia, hora_inicio, hora_fin in slots_a_probar:
                print(f"[TAILOR] Probando grupo {grupo['id_grupo_clase']} "
                    f"-> {dia} {hora_inicio}-{hora_fin}, {cantidad} estudiantes")
            

                cur.execute("""
                    SELECT
                        e.id_espacio,
                        e.nombre,
                        e.codigo,
                        e.capacidad,
                        e.tiene_computadores,
                        e.permite_portatiles,
                        e.es_laboratorio,
                        e.especialidad,
                        (e.capacidad - %s) AS diferencia,

                        (
                            SELECT COUNT(*)
                            FROM horario_semestre hs2
                            WHERE hs2.id_espacio = e.id_espacio
                            AND hs2.estado = 'Activo'
                        ) AS carga_total,

                        (
                            SELECT COUNT(*)
                            FROM horario_semestre hs3
                            WHERE hs3.id_espacio = e.id_espacio
                            AND hs3.estado = 'Activo'
                            AND hs3.dia_semana = %s
                        ) AS carga_dia

                    FROM espacio e
                    WHERE e.estado = 'Disponible'
                    AND e.capacidad >= %s

                    AND (
                        %s = 0
                        OR e.tiene_computadores = 1
                        OR e.permite_portatiles = 1
                    )

                    AND (
                        %s = 0
                        OR e.es_laboratorio = 1
                    )

                    AND NOT EXISTS (
                        SELECT 1
                        FROM horario_semestre hs
                        WHERE hs.id_espacio = e.id_espacio
                        AND hs.estado = 'Activo'
                        AND hs.dia_semana = %s
                        AND (
                            (%s >= hs.hora_inicio AND %s < hs.hora_fin)
                            OR (%s > hs.hora_inicio AND %s <= hs.hora_fin)
                            OR (%s <= hs.hora_inicio AND %s >= hs.hora_fin)
                        )
                    )

                    AND NOT EXISTS (
                        SELECT 1
                        FROM mantenimiento m
                        WHERE m.id_espacio = e.id_espacio
                        AND m.fecha_inicio <= %s
                        AND m.fecha_fin >= %s
                    )

                    ORDER BY
                        CASE
                            WHEN %s IS NOT NULL AND e.especialidad = %s THEN 0
                            ELSE 1
                        END,

                        CASE
                            WHEN %s <= 40 AND e.capacidad <= 40 THEN 0
                            WHEN %s > 40 AND e.capacidad > 40 THEN 0
                            ELSE 1
                        END,

                        carga_total ASC,
                        carga_dia ASC,
                        diferencia ASC,
                        RAND()

                    LIMIT 1
                """, (
                        cantidad,
                        dia,
                        cantidad,
                        int(grupo["requiere_computadores"] or 0),
                        int(grupo["requiere_laboratorio"] or 0),
                        dia,
                        hora_inicio, hora_inicio,
                        hora_fin, hora_fin,
                        hora_inicio, hora_fin,
                        fecha_fin, fecha_inicio,
                        grupo["especialidad_requerida"],
                        grupo["especialidad_requerida"],
                        cantidad,
                        cantidad,
                    )
                )
                espacio = cur.fetchone()

                if espacio:
                    slot_elegido = (dia, hora_inicio, hora_fin)
                    break

            if not espacio:
                print(f"[TAILOR] Grupo {grupo['id_grupo_clase']}: sin espacio disponible en ningún slot.")
                rechazadas.append({
                    "grupo_id": grupo["id_grupo_clase"],
                    "clase": grupo["clase_nombre"],
                    "motivo": "No se encontró espacio disponible con capacidad, recursos y horarios disponibles."
                })

                registrar_auditoria_mongo(
                    "ASIGNACION_FALLIDA",
                    "TailorMade",
                    f"No se pudo asignar salón para {grupo['clase_nombre']}",
                    usuario_id=session.get("user_id"),
                    extra={
                        "grupo_id": grupo["id_grupo_clase"],
                        "cantidad_estudiantes": cantidad,
                        "tipo_clase": grupo["tipo_clase"],
                        "requiere_computadores": bool(grupo["requiere_computadores"]),
                        "requiere_laboratorio": bool(grupo["requiere_laboratorio"]),
                    }
                )
                continue

            dia, hora_inicio, hora_fin = slot_elegido

            

            criterio = "Menor diferencia positiva de capacidad y cumplimiento de recursos requeridos"

            # ── Guardar horario semestral ────────────────────────────────────
            cur.execute("""
                INSERT INTO horario_semestre (
                    id_grupo_clase,
                    id_espacio,
                    id_usuario_docente,
                    dia_semana,
                    hora_inicio,
                    hora_fin,
                    fecha_inicio_semestre,
                    fecha_fin_semestre,
                    cantidad_estudiantes,
                    diferencia_capacidad,
                    criterio_asignacion
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                grupo["id_grupo_clase"],
                espacio["id_espacio"],
                id_docente,
                dia,
                hora_inicio,
                hora_fin,
                fecha_inicio,
                fecha_fin,
                cantidad,
                espacio["diferencia"],
                criterio,
            ))
            id_horario = cur.lastrowid
            print(f"[TAILOR] horario_semestre id={id_horario} insertado.")

            # ── Crear reservas semanales (una por fecha) ─────────────────────
            fechas = _fechas_recurrentes(fecha_inicio, fecha_fin, dia)
            print(f"[TAILOR] Grupo {grupo['id_grupo_clase']} -> {len(fechas)} fechas a reservar.")

            reservas_creadas_grupo   = 0
            reservas_conflicto_grupo = 0

            for fecha in fechas:
                # Verificar conflicto explícitamente antes de insertar
                cur.execute("""
                    SELECT COUNT(*) AS total
                    FROM reserva r
                    WHERE r.id_espacio      = %s
                      AND r.fecha_reserva   = %s
                      AND r.estado_reserva  = 'Activa'
                      AND (
                        (%s >= r.hora_inicio AND %s < r.hora_fin)
                        OR (%s > r.hora_inicio AND %s <= r.hora_fin)
                        OR (%s <= r.hora_inicio AND %s >= r.hora_fin)
                      )
                """, (
                    espacio["id_espacio"],
                    fecha,
                    hora_inicio, hora_inicio,
                    hora_fin,    hora_fin,
                    hora_inicio, hora_fin,
                ))
                conflicto = cur.fetchone()

                if conflicto and conflicto["total"] > 0:
                    reservas_conflicto_grupo += 1
                    continue

                # Insertar reserva — usar columnas origen e id_horario si ya existen.
                # Si aún no has corrido el ALTER TABLE, cambia el INSERT al bloque
                # comentado al final de este archivo.
                cur.execute("""
                    INSERT INTO reserva (
                        id_usuario,
                        id_espacio,
                        fecha_reserva,
                        hora_inicio,
                        hora_fin,
                        estado_reserva,
                        origen,
                        id_horario
                    )
                    VALUES (%s, %s, %s, %s, %s, 'Activa', 'SEMESTRAL', %s)
                """, (
                    id_docente or session["user_id"],
                    espacio["id_espacio"],
                    fecha,
                    hora_inicio,
                    hora_fin,
                    id_horario,
                ))
                reservas_creadas_grupo += 1

            print(f"[TAILOR] Grupo {grupo['id_grupo_clase']}: "
                  f"{reservas_creadas_grupo} reservas creadas, "
                  f"{reservas_conflicto_grupo} conflictos omitidos.")

            total_reservas_creadas   += reservas_creadas_grupo
            total_reservas_conflicto += reservas_conflicto_grupo

            asignadas.append({
                "id_horario":         id_horario,
                "clase":              grupo["clase_nombre"],
                "grupo":              grupo["codigo_grupo"],
                "cantidad_estudiantes": cantidad,
                "salon":              espacio["nombre"],
                "capacidad":          espacio["capacidad"],
                "diferencia":         espacio["diferencia"],
                "dia":                dia,
                "hora_inicio":        hora_inicio,
                "hora_fin":           hora_fin,
                "docente_id":         id_docente,
                "reservas_creadas":   reservas_creadas_grupo,
                "reservas_conflicto": reservas_conflicto_grupo,
            })

            registrar_auditoria_mongo(
                "ASIGNACION_SEMESTRAL", "TailorMade",
                f"Asignación semestral de {grupo['clase_nombre']} al espacio {espacio['nombre']}",
                usuario_id=session.get("user_id"),
                extra={
                    "id_horario":           id_horario,
                    "grupo_id":             grupo["id_grupo_clase"],
                    "clase":                grupo["clase_nombre"],
                    "grupo":                grupo["codigo_grupo"],
                    "cantidad_estudiantes": cantidad,
                    "espacio_id":           espacio["id_espacio"],
                    "salon":                espacio["nombre"],
                    "capacidad_salon":      espacio["capacidad"],
                    "diferencia_capacidad": espacio["diferencia"],
                    "dia":                  dia,
                    "hora_inicio":          hora_inicio,
                    "hora_fin":             hora_fin,
                    "criterio":             criterio,
                    "reservas_creadas":     reservas_creadas_grupo,
                }
            )

        # ── 4. Commit único al final de todo el proceso ──────────────────────
        db.commit()
        print(f"[TAILOR] Commit realizado. "
              f"Asignadas={len(asignadas)}, Rechazadas={len(rechazadas)}, "
              f"Reservas creadas={total_reservas_creadas}, "
              f"Conflictos omitidos={total_reservas_conflicto}")

        return jsonify({
            "ok":                      True,
            "msg":                     "Asignación semestral finalizada.",
            "total_asignadas":         len(asignadas),
            "total_rechazadas":        len(rechazadas),
            "total_reservas_creadas":  total_reservas_creadas,
            "total_reservas_conflicto": total_reservas_conflicto,
            "asignadas":               asignadas,
            "rechazadas":              rechazadas,
        })

    except Exception as exc:
        db.rollback()
        print(f"[TAILOR] asignar_semestre ERROR: {exc}")
        return jsonify({
            "ok":    False,
            "error": "Error ejecutando la asignación semestral."
        }), 500

    finally:
        cur.close()
        db.close()


@tailor_bp.route("/horarios")
@login_required
def listar_horarios():
    """
    Admin ve todos los horarios.
    Docente ve solo los suyos.
    """
    db  = get_db()
    cur = dict_cursor(db)

    try:
        base = """
            SELECT
                hs.id_horario,
                c.nombre          AS clase,
                g.codigo_grupo,
                g.cantidad_estudiantes,
                e.nombre          AS espacio,
                e.capacidad,
                hs.dia_semana,
                hs.hora_inicio,
                hs.hora_fin,
                hs.fecha_inicio_semestre,
                hs.fecha_fin_semestre,
                u.nombre          AS docente
            FROM horario_semestre hs
            JOIN grupo_clase g ON g.id_grupo_clase = hs.id_grupo_clase
            JOIN clase       c ON c.id_clase       = g.id_clase
            JOIN espacio     e ON e.id_espacio     = hs.id_espacio
            LEFT JOIN usuario u ON u.id_usuario    = hs.id_usuario_docente
            WHERE hs.estado = 'Activo'
        """
        params = []

        if session.get("rol") == "Docente":
            base += " AND hs.id_usuario_docente = %s"
            params.append(session["user_id"])

        base += (
            " ORDER BY "
            "FIELD(hs.dia_semana,'Lunes','Martes','Miércoles','Jueves','Viernes','Sábado'), "
            "hs.hora_inicio"
        )

        cur.execute(base, params)
        rows = cur.fetchall()

        for row in rows:
            row["hora_inicio"]            = str(row["hora_inicio"])
            row["hora_fin"]               = str(row["hora_fin"])
            row["fecha_inicio_semestre"]  = str(row["fecha_inicio_semestre"])
            row["fecha_fin_semestre"]     = str(row["fecha_fin_semestre"])

        return jsonify({"ok": True, "horarios": rows})

    finally:
        cur.close()
        db.close()


@tailor_bp.route("/limpiar-asignacion", methods=["POST"])
@admin_required
def limpiar_asignacion_automatica():
    """
    Borra las reservas y horarios generados automáticamente por Tailor Made.
    Sirve para limpiar pruebas sin borrar reservas manuales.
    """
    db = get_db()
    cur = dict_cursor(db)

    try:
        cur.execute("""
            DELETE FROM reserva
            WHERE origen = 'SEMESTRAL'
        """)
        reservas_borradas = cur.rowcount

        cur.execute("""
            DELETE FROM horario_semestre
            WHERE estado = 'Activo'
        """)
        horarios_borrados = cur.rowcount

        db.commit()

        registrar_auditoria_mongo(
            "LIMPIAR_ASIGNACION_SEMESTRAL",
            "TailorMade",
            "Administrador eliminó reservas y horarios semestrales generados automáticamente.",
            usuario_id=session.get("user_id"),
            extra={
                "reservas_borradas": reservas_borradas,
                "horarios_borrados": horarios_borrados
            }
        )

        return jsonify({
            "ok": True,
            "msg": "Asignación automática eliminada correctamente.",
            "reservas_borradas": reservas_borradas,
            "horarios_borrados": horarios_borrados
        })

    except Exception as exc:
        db.rollback()
        print(f"[TAILOR] limpiar asignación: {exc}")
        return jsonify({
            "ok": False,
            "error": "No se pudo limpiar la asignación automática."
        }), 500

    finally:
        cur.close()
        db.close()

# ─────────────────────────────────────────────────────────────────────────────
# Fallback INSERT without origen/id_horario columns
# (use this block if you have NOT yet run the ALTER TABLE migration)
# ─────────────────────────────────────────────────────────────────────────────
#
#   cur.execute("""
#       INSERT INTO reserva (
#           id_usuario, id_espacio, fecha_reserva,
#           hora_inicio, hora_fin, estado_reserva
#       )
#       VALUES (%s, %s, %s, %s, %s, 'Activa')
#   """, (
#       id_docente or session["user_id"],
#       espacio["id_espacio"],
#       fecha,
#       hora_inicio,
#       hora_fin,
#   ))