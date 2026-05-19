// ===============================
// SGEC - FRONT DASHBOARD
// ===============================

let ESPACIOS = [];
let BLOQUE_SELECCIONADO = null;
let RESERVAS_PROX = [];

// Rol del usuario obtenido del HTML
const USER_ROLE = document.querySelector(".user-name")?.dataset.userRol || "Estudiante";

document.addEventListener("DOMContentLoaded", () => {
  initDashboard();
});

async function initDashboard() {
  await Promise.all([
    cargarEspacios(),
    cargarDashboard(),
    cargarReservasProximas()
  ]);

  renderCalendar();
  wireModal();
}

async function deleteMaintenance() {
    const id = document.getElementById("mMantenimientoId").value;

    if (!confirm("¿Seguro que quieres eliminar este mantenimiento?")) return;

    const resp = await fetch(`/api/mantenimientos/eliminar/${id}`, {
        method: "DELETE"
    });

    const data = await resp.json();

    if (data.ok) {
        alert("Mantenimiento eliminado");
        closeMaintenanceModal();
        cargarEspacios();
    } else {
        alert("Error: " + data.error);
    }
}


// ===============================
// CARGA DE DATOS
// ===============================

async function cargarEspacios() {
  try {
    const res = await fetch("/api/espacios");
    if (!res.ok) throw new Error("Error al cargar espacios");
    ESPACIOS = await res.json();

    renderRoomList();
    renderEspaciosSelect();
    renderMapaBloques();
  } catch (err) {
    console.error(err);
  }
}

async function eliminarReserva(id_reserva) {
  if (!confirm("¿Seguro que deseas eliminar esta reserva?")) return;

  const resp = await fetch(`/api/reservas/${id_reserva}/eliminar`, {
    method: "DELETE"
  });

  const data = await resp.json();

  if (data.ok) {
    alert("Reserva eliminada correctamente");
    cargarReservas();  // refrescar reservaciones
    cargarEspacios();  // refrescar estados del mapa/lista
  } else {
    alert("Error: " + data.error);
  }
}


async function cargarDashboard() {
  try {
    const res = await fetch("/api/dashboard");
    if (!res.ok) throw new Error("Error al cargar dashboard");
    const stats = await res.json();

    setText("statEspacios", stats.espacios ?? 0);
    setText("statDisponibles", stats.espacios_disponibles ?? 0);
    setText("statHoy", stats.reservas_hoy ?? 0);
    setText("statMias", stats.mis_reservas ?? 0);
  } catch (err) {
    console.error(err);
  }
}

async function cargarReservasProximas() {
  try {
    const res = await fetch("/api/reservas/proximas");
    if (!res.ok) throw new Error("Error al cargar próximas reservas");
    RESERVAS_PROX = await res.json();
    renderUpcomingList();
  } catch (err) {
    console.error(err);
  }
}

// ===============================
// UTILIDADES DOM
// ===============================

function $(sel) {
  return document.querySelector(sel);
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

// ===============================
// LISTA DE ESPACIOS (COLUMNA IZQUIERDA)
// ===============================

function getBloqueDeNombre(nombre) {
  if (!nombre || typeof nombre !== "string") return null;
  return nombre.trim()[0].toUpperCase();
}

function espaciosFiltradosPorBloque() {
  if (!BLOQUE_SELECCIONADO) return ESPACIOS;
  return ESPACIOS.filter(e => getBloqueDeNombre(e.nombre) === BLOQUE_SELECCIONADO);
}

function renderRoomList() {
  const cont = document.getElementById("roomList");
  if (!cont) return;

  const searchValue = (document.getElementById("searchEspacio")?.value || "").toLowerCase();
  let data = espaciosFiltradosPorBloque();

  if (searchValue) {
    data = data.filter(e =>
      e.nombre.toLowerCase().includes(searchValue) ||
      (e.descripcion || "").toLowerCase().includes(searchValue)
    );
  }

  if (!data.length) {
    cont.innerHTML = `<div style="font-size:13px;color:var(--muted)">No hay espacios para el filtro actual.</div>`;
    return;
  }

  cont.innerHTML = data.map(e => {
    const estado = (e.estado || "Disponible").toLowerCase();

    let dotClass = "disponible";
    let disabledClass = "";
    let clickAction = `onclick="handleRoomClick(${e.id_espacio})"`;

    // Si está en mantenimiento → bloquear sala
    if (estado.includes("manten")) {
      dotClass = "mantenimiento";
      disabledClass = "room-disabled";
      clickAction = ""; // evita abrir el modal de reservas
    }
    else if (!estado.includes("dispon")) {
      dotClass = "ocupado";
    }

    return `
      <div class="room ${disabledClass}">
        <div class="room-main" ${clickAction}>
          <div class="dot ${dotClass}"></div>
          <div>
            <strong>${e.nombre}</strong>
            <div class="meta">
              Estado: ${e.estado}<br>
              Capacidad: ${e.capacidad ?? "-"}
            </div>
          </div>
        </div>

        ${
          USER_ROLE === "Administrador"
            ? `
              <button class="btn btn-small"
                      style="margin-top:6px"
                      onclick="openMaintenanceModal(${e.id_espacio})">
                🛠 Mantenimiento
              </button>
            `
            : ""
        }
      </div>
    `;
  }).join("");
}


// búsqueda por texto
const searchInput = document.getElementById("searchEspacio");
if (searchInput) {
  searchInput.addEventListener("input", () => renderRoomList());
}

// ===============================
// MANTENIMIENTO - MODAL
// ===============================

function openMaintenanceModal(idEspacio) {
  const idInput = document.getElementById("mEspacioId");
  const modal = document.getElementById("modalMantenimiento");

  if (!idInput || !modal) return;

  idInput.value = idEspacio;
  modal.classList.add("show");
}

function closeMaintenanceModal() {
  const modal = document.getElementById("modalMantenimiento");
  if (!modal) return;
  modal.classList.remove("show");
}

// ===============================
// SELECT DE ESPACIOS EN EL MODAL
// ===============================

function renderEspaciosSelect() {
  const sel = document.getElementById("fEspacio");
  if (!sel) return;

  const data = espaciosFiltradosPorBloque();

  sel.innerHTML = `
    <option value="">Selecciona un espacio...</option>
    ${data.map(e => `<option value="${e.id_espacio}">${e.nombre} - ${e.descripcion || ""}</option>`).join("")}
  `;
}

// ===============================
// MAPA SVG DE BLOQUES (COLUMNA CENTRAL)
// ===============================

function renderMapaBloques() {
  const cont = document.getElementById("mapaSvg");
  if (!cont) return;

  cont.innerHTML = `
    <div class="campus-map-real">
      <!-- Zonas verdes y circulación -->
      <div class="campus-zone green zone-1"></div>
      <div class="campus-zone green zone-2"></div>
      <div class="campus-zone green zone-3"></div>
      <div class="campus-zone path zone-path-main"></div>

      <!-- Bloques válidos: A, B, C, E, F, G, I, M, O -->
      <button class="campus-block block-a" data-bloque="A">A</button>
      <button class="campus-block block-b" data-bloque="B">B</button>
      <button class="campus-block block-c" data-bloque="C">C</button>
      <button class="campus-block block-e" data-bloque="E">E</button>
      <button class="campus-block block-f" data-bloque="F">F</button>
      <button class="campus-block block-g" data-bloque="G">G</button>
      <button class="campus-block block-i" data-bloque="I">I</button>
      <button class="campus-block block-j" data-bloque="J">J</button>
      <button class="campus-block block-m" data-bloque="M">M</button>
      <button class="campus-block block-o" data-bloque="O">O</button>

      <div class="map-label label-entrada">Entrada principal</div>
      <div class="map-label label-campus">Campus académico</div>
      <div class="map-label label-medical">Los Cobos Medical Center</div>
    </div>
  `;

  if (BLOQUE_SELECCIONADO) {
    const selected = cont.querySelector(`[data-bloque="${BLOQUE_SELECCIONADO}"]`);
    if (selected) selected.classList.add("selected");
  }

  cont.querySelectorAll(".campus-block").forEach(btn => {
    btn.addEventListener("click", () => {
      seleccionarBloque(btn.dataset.bloque);
    });
  });
}

function seleccionarBloque(bloqueId) {
  if (BLOQUE_SELECCIONADO === bloqueId) {
    BLOQUE_SELECCIONADO = null;
  } else {
    BLOQUE_SELECCIONADO = bloqueId;
  }

  renderMapaBloques();
  renderRoomList();
  renderEspaciosSelect();

  const searchInput = document.getElementById("searchEspacio");
  if (searchInput) {
    searchInput.value = BLOQUE_SELECCIONADO || "";
  }
}

// ===============================
// CALENDARIO SEMANAL
// ===============================

function renderCalendar() {
  const cont = document.getElementById("calendar");
  if (!cont) return;

  const hoy = new Date();
  const diasSemana = [];

  for (let i = 0; i < 7; i++) {
    const d = new Date(hoy);
    d.setDate(hoy.getDate() + i);
    diasSemana.push(d);
  }

  const nombres = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];

  cont.innerHTML = diasSemana.map(d => {
    const nombreDia = nombres[d.getDay()];
    const fechaStr = d.toISOString().substring(0, 10);

    return `
      <div class="day" onclick="abrirReservaParaFecha('${fechaStr}')">
        <div class="date">${nombreDia} ${d.getDate()}</div>
      </div>
    `;
  }).join("");
}

function abrirReservaParaFecha(fechaISO) {
  if (USER_ROLE === "Estudiante") {
    alert("Como estudiante solo puedes visualizar el calendario.");
    return;
  }
  openModal();
  const inputFecha = document.getElementById("fFecha");
  if (inputFecha) inputFecha.value = fechaISO;
}

// ===============================
// PRÓXIMAS RESERVAS (COLUMNA DERECHA)
// ===============================

function renderUpcomingList() {
  const cont = document.getElementById("upcomingList");
  if (!cont) return;

  if (!RESERVAS_PROX.length) {
    cont.innerHTML = `<div style="font-size:13px;color:var(--muted)">No tienes reservas próximas</div>`;
    return;
  }

  cont.innerHTML = RESERVAS_PROX.map(r => `
    <div class="upcoming-item">
      <strong>${r.espacio_nombre}</strong>
      <div class="meta">
        ${r.fecha_reserva} · ${r.hora_inicio} - ${r.hora_fin}
      </div>

      ${USER_ROLE === "Administrador" ? `
        <button 
          class="btn btn-small btn-danger" 
          style="margin-top:6px"
          onclick="deleteReserva(${r.id_reserva})">
          Eliminar reserva
        </button>
      ` : ""}
    </div>
  `).join("");
}

function openGlobalReservasModal() {
  document.getElementById("modalReservasGlobal").classList.add("show");
  cargarTodasLasReservas();
}

function closeGlobalReservasModal() {
  document.getElementById("modalReservasGlobal").classList.remove("show");
}

async function cargarTodasLasReservas() {
  const cont = document.getElementById("listaReservasGlobal");
  cont.innerHTML = "<p style='color:var(--muted)'>Cargando...</p>";

  try {
    const resp = await fetch("/api/admin/reservas/all");
    const data = await resp.json();

    if (!data.length) {
      cont.innerHTML = "<p style='color:var(--muted)'>No hay reservas registradas</p>";
      return;
    }

    cont.innerHTML = data.map(r => `
      <div class="reserva-item" style="padding:10px;border-bottom:1px solid #234">
        <strong>${r.espacio_nombre}</strong> — ${r.usuario}
        <br>
        ${r.fecha_reserva} | ${r.hora_inicio} - ${r.hora_fin}
        <br>
        <button class="btn btn-danger btn-small" 
                onclick="deleteReserva(${r.id_reserva})"
                style="margin-top:5px">
          Eliminar
        </button>
      </div>
    `).join("");

  } catch (err) {
    cont.innerHTML = "<p style='color:#e66'>Error cargando reservas</p>";
  }
}

// ===============================
// MODAL DE RESERVA
// ===============================

function wireModal() {
  const form = document.getElementById("formReserva");
  if (!form) return;

  form.addEventListener("submit", async e => {
    e.preventDefault();

    if (USER_ROLE === "Estudiante") {
      alert("Como estudiante no puedes crear reservas.");
      return;
    }

    const espacioId = document.getElementById("fEspacio").value;
    const fecha = document.getElementById("fFecha").value;
    const horaInicio = document.getElementById("fHoraInicio").value;
    const horaFin = document.getElementById("fHoraFin").value;

    if (!espacioId || !fecha || !horaInicio || !horaFin) {
      alert("Por favor completa todos los campos.");
      return;
    }

    // Validación de horario 7:00–22:00
    if (horaInicio < "07:00" || horaFin > "22:00" || horaFin <= horaInicio) {
      alert("Las reservas deben ser entre las 7:00 a.m. y las 10:00 p.m., y la hora de fin debe ser mayor que la de inicio.");
      return;
    }

    try {
      const resp = await fetch("/api/reservas", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_espacio: parseInt(espacioId, 10),
          fecha_reserva: fecha,
          hora_inicio: horaInicio,
          hora_fin: horaFin
        })
      });

      const data = await resp.json();

      if (data.ok) {
        alert("Reserva creada correctamente.");
        closeModal();
        cargarReservasProximas();
        cargarDashboard();
      } else {
        alert(data.error || data.msg || "No se pudo crear la reserva.");
      }
    } catch (err) {
      console.error(err);
      alert("Error de conexión con el servidor.");
    }
  });
}

async function deleteReserva(id_reserva) {
  if (!confirm("¿Seguro que deseas eliminar esta reserva?")) return;

  try {
    const resp = await fetch(`/api/reservas/${id_reserva}`, {
      method: "DELETE"
    });

    const data = await resp.json();

    if (data.ok) {
      alert("Reserva eliminada correctamente");
      // Refrescamos datos
      cargarReservasProximas();
      cargarDashboard();
      cargarEspacios();
    } else {
      alert(data.error || "No se pudo eliminar la reserva");
    }
  } catch (err) {
    console.error(err);
    alert("Error de conexión con el servidor");
  }
}

// Exponerla para que HTML pueda llamarla
window.deleteReserva = deleteReserva;


function handleRoomClick(espacioId) {
  if (USER_ROLE === "Estudiante") {
    alert("Como estudiante solo puedes visualizar la disponibilidad.");
    return;
  }
  openModal(espacioId);
}

function openModal(espacioId = null) {
  const modal = document.getElementById("modalReserva");
  if (!modal) return;

  modal.classList.add("show");

  const sel = document.getElementById("fEspacio");
  if (sel) {
    renderEspaciosSelect();
    if (espacioId) sel.value = String(espacioId);
  }

  const inputFecha = document.getElementById("fFecha");
  if (inputFecha && !inputFecha.value) {
    const hoy = new Date().toISOString().substring(0, 10);
    inputFecha.value = hoy;
  }
}

function closeModal() {
  const modal = document.getElementById("modalReserva");
  if (!modal) return;
  modal.classList.remove("show");
}

// Botón "+ Nueva" en la columna derecha
function openModalNuevoEspacio() {
  if (USER_ROLE !== "Administrador") {
    alert("Solo el administrador puede crear reservas. Los docentes deben abrir tickets.");
    return;
  }
  openModal();
}

// ===============================
// EXPORTAR REPORTE (BOTÓN)
// ===============================

function exportarReporte() {
    window.open("/api/reportes/historial", "_blank");
}




// ===============================
// LISTENER FORM MANTENIMIENTO
// ===============================

const maintForm = document.getElementById("formMantenimiento");

if (maintForm) {
  maintForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const fi = document.getElementById("mFechaInicio").value;
    const ff = document.getElementById("mFechaFin").value;
    const desc = document.getElementById("mDescripcion").value;

    if (!fi || !ff) {
      alert("Debes seleccionar fecha de inicio y fecha de fin.");
      return;
    }

    const payload = {
      id_espacio: document.getElementById("mEspacioId").value,
      fecha_inicio: fi,
      fecha_fin: ff,
      descripcion: desc,
    };

    const resp = await fetch("/api/mantenimientos/crear", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const data = await resp.json();

    if (data.ok) {
      alert("Mantenimiento asignado correctamente");
      closeMaintenanceModal();
      cargarEspacios(); // refrescar lista
    } else {
      alert("Error: " + data.error);
    }
  });
}

// ===============================
// TAILOR MADE SEMESTRAL
// ===============================

function openTailorModal() {
  const modal = document.getElementById("modalTailor");
  const inicio = document.getElementById("fechaInicioSemestre");
  const fin = document.getElementById("fechaFinSemestre");
  const cont = document.getElementById("tailorResultados");

  if (!modal) return;

  if (inicio && !inicio.value) {
    inicio.value = "2026-02-02";
  }

  if (fin && !fin.value) {
    fin.value = "2026-06-12";
  }

  if (cont) {
    cont.innerHTML = `
      <p style="color:var(--muted)">
        Selecciona las fechas del semestre y presiona <strong>Confirmar asignación</strong>.
      </p>
    `;
  }

  modal.classList.add("show");
}

function closeTailorModal() {
  const modal = document.getElementById("modalTailor");
  if (modal) {
    modal.classList.remove("show");
  }
}

async function confirmarAsignacionSemestre() {
  const inicio = document.getElementById("fechaInicioSemestre")?.value;
  const fin = document.getElementById("fechaFinSemestre")?.value;
  const cont = document.getElementById("tailorResultados");

  if (!inicio || !fin) {
    alert("Debes seleccionar la fecha de inicio y la fecha de fin del semestre.");
    return;
  }

  if (new Date(fin) <= new Date(inicio)) {
    alert("La fecha final debe ser mayor que la fecha inicial.");
    return;
  }

  const confirmar = confirm(
    `¿Deseas ejecutar la asignación automática del semestre desde ${inicio} hasta ${fin}?`
  );

  if (!confirmar) return;

  if (cont) {
    cont.innerHTML = `
      <p style="color:var(--muted)">
        Ejecutando asignación automática. Esto puede tardar unos segundos...
      </p>
    `;
  }

  try {
    const resp = await fetch("/api/tailor/asignar-semestre", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        fecha_inicio: inicio,
        fecha_fin: fin
      })
    });

    const data = await resp.json();

    if (!data.ok) {
      cont.innerHTML = `
        <p style="color:#ff6b8a">
          ${data.error || "Error ejecutando la asignación automática."}
        </p>
      `;
      return;
    }

    cont.innerHTML = `
      <div class="stats" style="margin-bottom:16px">
        <div class="stat">
          <div>
            <div class="stat-label">Horarios asignados</div>
            <div class="stat-value">${data.total_asignadas}</div>
          </div>
          <div class="stat-badge">OK</div>
        </div>

        <div class="stat">
          <div>
            <div class="stat-label">Grupos rechazados</div>
            <div class="stat-value">${data.total_rechazadas}</div>
          </div>
          <div class="stat-badge">Revisar</div>
        </div>

        <div class="stat">
          <div>
            <div class="stat-label">Reservas creadas</div>
            <div class="stat-value">${data.total_reservas_creadas || 0}</div>
          </div>
          <div class="stat-badge">Semestre</div>
        </div>

        <div class="stat">
          <div>
            <div class="stat-label">Conflictos omitidos</div>
            <div class="stat-value">${data.total_reservas_conflicto || 0}</div>
          </div>
          <div class="stat-badge">Choques</div>
        </div>
      </div>

      <h4>Asignaciones realizadas</h4>

      <div style="overflow-x:auto">
        <table class="tabla-mongo">
          <thead>
            <tr>
              <th>Clase</th>
              <th>Grupo</th>
              <th>Estudiantes</th>
              <th>Salón</th>
              <th>Capacidad</th>
              <th>Diferencia</th>
              <th>Día</th>
              <th>Horario</th>
              <th>Reservas</th>
            </tr>
          </thead>
          <tbody>
            ${(data.asignadas || []).map(a => `
              <tr>
                <td>${a.clase}</td>
                <td>${a.grupo}</td>
                <td>${a.cantidad_estudiantes}</td>
                <td>${a.salon}</td>
                <td>${a.capacidad}</td>
                <td>${a.diferencia}</td>
                <td>${a.dia}</td>
                <td>${a.hora_inicio} - ${a.hora_fin}</td>
                <td>${a.reservas_creadas || 0}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;

    if (typeof cargarDashboard === "function") cargarDashboard();
    if (typeof cargarReservasProximas === "function") cargarReservasProximas();
    if (typeof cargarEspacios === "function") cargarEspacios();

  } catch (error) {
    console.error(error);

    if (cont) {
      cont.innerHTML = `
        <p style="color:#ff6b8a">
          Error inesperado ejecutando la asignación automática.
        </p>
      `;
    }
  }
}

function closeTailorModal() {
  document.getElementById("modalTailor").classList.remove("show");
}

async function generarCuposAleatorios() {
  if (!confirm("¿Generar cantidades aleatorias de estudiantes para todos los grupos?")) return;

  const resp = await fetch("/api/tailor/generar-cupos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      minimo: 18,
      maximo: 70
    })
  });

  const data = await resp.json();

  if (data.ok) {
    alert(data.msg);
  } else {
    alert(data.error || "Error generando cupos");
  }
}

async function asignarSemestreTailor() {
  openTailorModal();

  const inicio = document.getElementById("fechaInicioSemestre").value || "2026-02-02";
  const fin = document.getElementById("fechaFinSemestre").value || "2026-06-12";

  const cont = document.getElementById("tailorResultados");
  cont.innerHTML = "<p style='color:var(--muted)'>Ejecutando asignación automática...</p>";

  const resp = await fetch("/api/tailor/asignar-semestre", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      fecha_inicio: inicio,
      fecha_fin: fin
    })
  });

  const data = await resp.json();

  if (!data.ok) {
    cont.innerHTML = `<p style="color:#ff6b8a">${data.error || "Error ejecutando asignación"}</p>`;
    return;
  }

  cont.innerHTML = `
    <div class="stat" style="margin-bottom:12px">
      <div>
        <div class="stat-label">Asignadas</div>
        <div class="stat-value">${data.total_asignadas}</div>
      </div>
      <div class="stat-badge">OK</div>
    </div>

    <div class="stat" style="margin-bottom:12px">
      <div>
        <div class="stat-label">Rechazadas</div>
        <div class="stat-value">${data.total_rechazadas}</div>
      </div>
      <div class="stat-badge">Revisar</div>
    </div>

    <h4>Asignaciones realizadas</h4>
    <div style="overflow-x:auto">
      <table class="tabla-mongo">
        <thead>
          <tr>
            <th>Clase</th>
            <th>Grupo</th>
            <th>Estudiantes</th>
            <th>Salón</th>
            <th>Capacidad</th>
            <th>Diferencia</th>
            <th>Día</th>
            <th>Horario</th>
          </tr>
        </thead>
        <tbody>
          ${data.asignadas.map(a => `
            <tr>
              <td>${a.clase}</td>
              <td>${a.grupo}</td>
              <td>${a.cantidad_estudiantes}</td>
              <td>${a.salon}</td>
              <td>${a.capacidad}</td>
              <td>${a.diferencia}</td>
              <td>${a.dia}</td>
              <td>${a.hora_inicio} - ${a.hora_fin}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;

  cargarDashboard();
  cargarReservasProximas();
  cargarEspacios();
}

async function cargarHorariosSemestre() {
  const resp = await fetch("/api/tailor/horarios");
  const data = await resp.json();

  if (!data.ok) {
    alert("No se pudieron cargar los horarios.");
    return;
  }

  openTablaGeneralModal("Horarios semestrales", `
    <div style="overflow-x:auto">
      <table class="tabla-mongo">
        <thead>
          <tr>
            <th>Clase</th>
            <th>Grupo</th>
            <th>Docente</th>
            <th>Espacio</th>
            <th>Día</th>
            <th>Horario</th>
            <th>Estudiantes</th>
            <th>Semestre</th>
          </tr>
        </thead>
        <tbody>
          ${data.horarios.map(h => `
            <tr>
              <td>${h.clase}</td>
              <td>${h.codigo_grupo}</td>
              <td>${h.docente || "-"}</td>
              <td>${h.espacio}</td>
              <td>${h.dia_semana}</td>
              <td>${h.hora_inicio} - ${h.hora_fin}</td>
              <td>${h.cantidad_estudiantes}</td>
              <td>${h.fecha_inicio_semestre} a ${h.fecha_fin_semestre}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `);
}

function cargarMisClasesDocente() {
  cargarHorariosSemestre();
}

// ===============================
// TICKETS DOCENTE / ADMIN
// ===============================

function openTicketModal() {
  document.getElementById("modalTicket").classList.add("show");
}

function closeTicketModal() {
  document.getElementById("modalTicket").classList.remove("show");
}

const formTicket = document.getElementById("formTicket");

if (formTicket) {
  formTicket.addEventListener("submit", async e => {
    e.preventDefault();

    const asunto = document.getElementById("ticketAsunto").value;
    const descripcion = document.getElementById("ticketDescripcion").value;

    const resp = await fetch("/api/tickets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ asunto, descripcion })
    });

    const data = await resp.json();

    if (data.ok) {
      alert("Ticket enviado correctamente.");
      closeTicketModal();
      formTicket.reset();
    } else {
      alert(data.error || "No se pudo enviar el ticket.");
    }
  });
}

async function cargarTickets() {
  const resp = await fetch("/api/tickets");
  const data = await resp.json();

  if (!data.ok) {
    alert("No se pudieron cargar los tickets.");
    return;
  }

  openTablaGeneralModal("Tickets", `
    <div style="overflow-x:auto">
      <table class="tabla-mongo">
        <thead>
          <tr>
            <th>ID</th>
            <th>Docente</th>
            <th>Asunto</th>
            <th>Descripción</th>
            <th>Estado</th>
            <th>Respuesta</th>
            <th>Fecha</th>
          </tr>
        </thead>
        <tbody>
          ${data.tickets.map(t => `
            <tr>
              <td>${t.id_ticket}</td>
              <td>${t.docente_nombre || "-"}</td>
              <td>${t.asunto}</td>
              <td>${t.descripcion}</td>
              <td>${t.estado}</td>
              <td>${t.respuesta_admin || "-"}</td>
              <td>${t.fecha_creacion}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `);
}

// ===============================
// MODAL TABLAS GENERAL
// ===============================

function openTablaGeneralModal(titulo, contenido) {
  document.getElementById("modalTablaTitulo").textContent = titulo;
  document.getElementById("modalTablaContenido").innerHTML = contenido;
  document.getElementById("modalTablaGeneral").classList.add("show");
}

function closeTablaGeneralModal() {
  document.getElementById("modalTablaGeneral").classList.remove("show");
}

async function limpiarAsignacionAutomatica() {
  const confirmar = confirm(
    "¿Seguro que deseas borrar las reservas y horarios generados automáticamente? Esta acción no borra reservas manuales."
  );

  if (!confirmar) return;

  try {
    const resp = await fetch("/api/tailor/limpiar-asignacion", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      }
    });

    const data = await resp.json();

    if (!data.ok) {
      alert(data.error || "No se pudo limpiar la asignación automática.");
      return;
    }

    alert(
      `${data.msg}\n\nReservas borradas: ${data.reservas_borradas}\nHorarios borrados: ${data.horarios_borrados}`
    );

    if (typeof cargarDashboard === "function") cargarDashboard();
    if (typeof cargarReservasProximas === "function") cargarReservasProximas();
    if (typeof cargarEspacios === "function") cargarEspacios();

  } catch (error) {
    console.error(error);
    alert("Error inesperado limpiando la asignación automática.");
  }
}

window.generarCuposAleatorios = generarCuposAleatorios;
window.asignarSemestreTailor = asignarSemestreTailor;
window.cargarHorariosSemestre = cargarHorariosSemestre;
window.cargarMisClasesDocente = cargarMisClasesDocente;
window.openTicketModal = openTicketModal;
window.closeTicketModal = closeTicketModal;
window.cargarTickets = cargarTickets;
window.closeTailorModal = closeTailorModal;
window.closeTablaGeneralModal = closeTablaGeneralModal;

// Exponer funciones que se usan desde HTML
window.openModal = openModal;
window.closeModal = closeModal;
window.openModalNuevoEspacio = openModalNuevoEspacio;
window.exportarReporte = exportarReporte;
window.abrirReservaParaFecha = abrirReservaParaFecha;
window.seleccionarBloque = seleccionarBloque;
window.openMaintenanceModal = openMaintenanceModal;
window.closeMaintenanceModal = closeMaintenanceModal;
window.handleRoomClick = handleRoomClick;
window.openGlobalReservasModal = openGlobalReservasModal;
window.closeGlobalReservasModal = closeGlobalReservasModal;
window.deleteReserva = deleteReserva;
window.openTailorModal = openTailorModal;
window.closeTailorModal = closeTailorModal;
window.confirmarAsignacionSemestre = confirmarAsignacionSemestre;
window.limpiarAsignacionAutomatica = limpiarAsignacionAutomatica;

