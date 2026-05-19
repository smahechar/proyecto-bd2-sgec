# SGEC - Sistema de Gestión de Espacios Colaborativos

SGEC es una aplicación web desarrollada con Python y Flask para gestionar espacios académicos de la Universidad El Bosque. El sistema permite consultar salones, laboratorios y espacios disponibles, gestionar reservas, mantenimientos, tickets docentes y ejecutar una asignación automática de salones para todo un semestre mediante una solución tipo Tailor Made.

El proyecto integra dos bases de datos:

- MySQL, para la información estructurada y operacional.
- MongoDB, para auditoría, trazabilidad, eventos de seguridad y estadísticas.

---

## Objetivo del proyecto

El objetivo del sistema es facilitar la gestión de espacios universitarios y apoyar la asignación de salones de forma más eficiente, teniendo en cuenta:

- Cantidad de estudiantes.
- Capacidad del salón.
- Tipo de clase.
- Recursos requeridos.
- Disponibilidad del espacio.
- Mantenimientos activos.
- Cruces de horario.
- Distribución durante toda la semana.
- Repetición de horarios durante el semestre.

---

## Tecnologías utilizadas

- Python
- Flask
- MySQL
- MongoDB
- HTML
- CSS
- JavaScript
- MySQL Workbench
- MongoDB Compass
- VirtualBox

---

## Arquitectura general

El sistema trabaja con una arquitectura híbrida.

### MySQL

MySQL almacena la información estructurada del sistema:

- Usuarios
- Roles
- Espacios
- Bloques
- Tipos de espacio
- Clases
- Grupos de clase
- Docentes asignados
- Reservas
- Horarios semestrales
- Mantenimientos
- Tickets docentes

### MongoDB

MongoDB almacena información flexible relacionada con auditoría y trazabilidad:

- Auditorías generales
- Eventos de asignación
- Eventos de seguridad
- Estadísticas
- Registros del algoritmo Tailor Made

Colecciones principales:

audit_logs
eventos_asignacion
eventos_seguridad
estadisticas

---

## Conexiones del proyecto

### MySQL

Host: 192.168.56.102
Puerto: 13306
Base de datos: bdatos2_sgec

### MongoDB

Host: 192.168.56.101
Puerto: 27018
Base de datos: sgec_logs

### Flask

http://127.0.0.1:5000

---

## Estructura del proyecto

proyecto-bd2-sgec/
│
├── Python/
│   ├── run.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── db.py
│   │   ├── decorators.py
│   │   ├── extensions.py
│   │   │
│   │   ├── routes/
│   │   │   ├── auth.py
│   │   │   ├── pages.py
│   │   │   ├── espacios.py
│   │   │   ├── reservas.py
│   │   │   ├── mantenimientos.py
│   │   │   ├── reportes.py
│   │   │   ├── mongo_reports.py
│   │   │   ├── tailor.py
│   │   │   └── tickets.py
│   │   │
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── formatting.py
│   │       └── security.py
│   │
│   ├── static/
│   │   ├── estilos.css
│   │   ├── main.js
│   │   └── logo_elbosque.png
│   │
│   └── templates/
│       ├── login.html
│       ├── registro.html
│       ├── main.html
│       ├── 404.html
│       └── 500.html
│
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md

---

## Funcionalidades principales

### Inicio de sesión

El sistema permite iniciar sesión con usuarios registrados en MySQL. Según el rol del usuario, se habilitan diferentes opciones en la interfaz.

Roles principales:

Administrador
Docente
Estudiante

---

### Gestión de espacios

El sistema permite consultar espacios disponibles, revisar su estado, capacidad, bloque y tipo de espacio.

Los espacios pueden tener estados como:

Disponible
Reservado
Mantenimiento

---

### Reservas manuales

El administrador puede crear reservas manuales sobre espacios disponibles.

Estas reservas se almacenan en la tabla reserva.

---

### Mantenimientos

El administrador puede registrar mantenimientos sobre espacios. Cuando un espacio está en mantenimiento, no debe ser asignado por el algoritmo automático.

---

### Tickets docentes

El docente no puede crear reservas manuales. En su lugar, puede abrir tickets relacionados con sus clases o espacios asignados.

El administrador puede consultar y gestionar estos tickets.

---

## Solución Tailor Made

La funcionalidad principal del proyecto es la asignación automática de salones para todo un semestre.

El módulo se encuentra en:

Python/app/routes/tailor.py

Rutas principales:

POST /api/tailor/generar-cupos
POST /api/tailor/asignar-semestre
GET  /api/tailor/horarios
POST /api/tailor/limpiar-asignacion

---

### Generación de cupos aleatorios

El sistema genera una cantidad de estudiantes para cada grupo de clase.

La generación busca ser realista:

- La mayoría de grupos queda por debajo de 40 estudiantes.
- Solo una minoría supera los 40 estudiantes.
- Esto evita que todos los grupos usen salones grandes.

---

### Asignación automática semestral

El administrador selecciona una fecha de inicio y una fecha final del semestre. Luego el sistema asigna automáticamente salones a los grupos activos.

El algoritmo considera:

cantidad de estudiantes
capacidad del salón
tipo de clase
requerimiento de computadores
requerimiento de laboratorio
especialidad del espacio
mantenimientos activos
cruces de horario
carga total del salón
carga del salón por día

---

### Horarios semestrales

Cuando el sistema asigna un salón, crea un registro en la tabla:

horario_semestre

Esta tabla representa el horario fijo de un grupo durante el semestre.

Ejemplo:

Clase: Bases de Datos 2
Grupo: 01
Salón: A203
Día: Lunes
Hora: 07:00 - 09:00
Fecha inicio: 2026-02-02
Fecha fin: 2026-06-12

---

### Reservas recurrentes

Después de crear el horario semestral, el sistema genera reservas semanales en la tabla:

reserva

Las reservas generadas por el algoritmo se identifican con:

origen = SEMESTRAL

Esto permite diferenciarlas de las reservas manuales.

---

### Limpieza de asignación automática

Para pruebas, existe una opción que elimina únicamente lo generado automáticamente:

POST /api/tailor/limpiar-asignacion

Esta opción borra:

reservas con origen = SEMESTRAL
horarios semestrales activos

No elimina reservas manuales.

---

## Auditoría con MongoDB

Cada acción importante del sistema puede registrarse en MongoDB.

Ejemplos de acciones auditadas:

LOGIN_OK
LOGIN_FAIL
LOGOUT
GENERAR_CUPOS_ALEATORIOS
ASIGNACION_SEMESTRAL
ASIGNACION_FALLIDA
LIMPIAR_ASIGNACION_SEMESTRAL
TICKET_CREATE
TICKET_UPDATE

Esto permite mantener trazabilidad sobre las acciones del sistema y sobre las decisiones tomadas por el algoritmo.

---

## Procedimientos almacenados

La base relacional puede incluir procedimientos almacenados para encapsular operaciones críticas, especialmente relacionadas con reservas.

Ejemplo de verificación en MySQL:

SHOW PROCEDURE STATUS
WHERE Db = 'bdatos2_sgec';

Ejemplo para revisar un procedimiento:

SHOW CREATE PROCEDURE crear_reserva;

La idea de los procedimientos almacenados es reforzar la validación desde la base de datos, por ejemplo:

- Verificar disponibilidad.
- Evitar cruces de horario.
- Validar existencia del espacio.
- Controlar estados de reserva.
- Evitar reservas en espacios en mantenimiento.

---

## Instalación y ejecución

### 1. Clonar el repositorio

git clone https://github.com/smahechar/proyecto-bd2-sgec.git
cd proyecto-bd2-sgec

---

### 2. Crear entorno virtual

python -m venv venv

Activar entorno virtual en Windows:

venv\Scripts\activate

---

### 3. Instalar dependencias

pip install -r requirements.txt

---

### 4. Configurar variables de entorno

Crear un archivo .env basado en .env.example.

Ejemplo:

SECRET_KEY=clave_sgec_bd2_segura_2026

DB_HOST=192.168.56.102
DB_PORT=13306
DB_USER=sgec_app
DB_PASS=********
DB_NAME=bdatos2_sgec

MONGO_HOST=192.168.56.101
MONGO_PORT=27018
MONGO_DB=sgec_logs

Nota: por seguridad, el archivo .env no debe subirse a GitHub.

---

### 5. Ejecutar la aplicación

Desde la carpeta Python:

cd Python
python run.py

Luego abrir en el navegador:

http://127.0.0.1:5000

---

## Consultas útiles de verificación

### Verificar horarios semestrales

USE bdatos2_sgec;

SELECT COUNT(*) AS horarios_activos
FROM horario_semestre
WHERE estado = 'Activo';

---

### Verificar reservas automáticas

SELECT COUNT(*) AS reservas_semestrales
FROM reserva
WHERE origen = 'SEMESTRAL';

---

### Ver distribución por salón

SELECT 
    e.codigo,
    e.capacidad,
    COUNT(*) AS total_horarios_asignados
FROM horario_semestre hs
JOIN espacio e ON e.id_espacio = hs.id_espacio
WHERE hs.estado = 'Activo'
GROUP BY e.codigo, e.capacidad
ORDER BY total_horarios_asignados DESC;

---

### Ver auditorías en MongoDB

use sgec_logs

db.audit_logs.find().sort({ fecha: -1 }).limit(5).pretty()

---

### Ver auditorías de asignación automática

db.audit_logs.find({ accion: "ASIGNACION_SEMESTRAL" })
  .sort({ fecha: -1 })
  .limit(5)
  .pretty()

---

## Estado actual del proyecto

El sistema cuenta con:

- Conexión funcional a MySQL.
- Conexión funcional a MongoDB.
- Login por roles.
- Dashboard principal.
- Gestión de espacios.
- Gestión de reservas.
- Gestión de mantenimientos.
- Tickets docentes.
- Reportes y auditorías MongoDB.
- Algoritmo Tailor Made para asignación semestral.
- Generación de reservas recurrentes.
- Limpieza de asignaciones automáticas.

---

## Autores

Proyecto desarrollado para la asignatura de Bases de Datos 2.

Universidad El Bosque
Ingeniería de Sistemas

Integrante:

Sergio Mahecha Rodríguez

---

## Nota final

Este proyecto demuestra el uso integrado de una base de datos relacional y una base de datos no relacional dentro de una aplicación web.

MySQL se utiliza para la persistencia estructurada del sistema, mientras que MongoDB permite manejar auditorías, eventos y trazabilidad de manera flexible.

La funcionalidad Tailor Made es el componente principal del proyecto, ya que automatiza la asignación de espacios académicos durante todo un semestre, considerando capacidad, disponibilidad, recursos y restricciones de horario.
