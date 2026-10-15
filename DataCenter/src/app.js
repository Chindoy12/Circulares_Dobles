const STATUS_LABELS = { PENDING: "Pendiente", IN_PROGRESS: "En ejecución", COMPLETED: "Completada", BLOCKED: "Bloqueada" };
const PRIORITY_LABELS = { LOW: "Baja", MEDIUM: "Media", HIGH: "Alta", CRITICAL: "Crítica" };
const EQUIPMENT_LABELS = { SERVER: "Servidor", COOLING: "Refrigeración", UPS: "UPS", NETWORK: "Red", STORAGE: "Almacenamiento", SENSOR: "Sensor ambiental" };
const SOURCE_LABELS = { DEMO: "Demo", USER: "Usuario" };
const CHECK_LABELS = {
  empty_list_consistent: "Lista vacía: head, current y size coherentes",
  bidirectional_links: "node.next.prev y node.prev.next apuntan al nodo",
  forward_cycle_returns_to_head: "Recorrido con next regresa a head",
  backward_cycle_returns_to_head: "Recorrido con prev regresa a head",
  tail_next_is_head: "tail.next es head",
  head_prev_is_tail: "head.prev es tail",
  size_matches_nodes: "size coincide con los nodos contados",
  current_in_list: "current pertenece a la lista",
  unique_task_ids: "Identificadores sin duplicados",
};
const FIELD_LABELS = {
  task_id: "identificador", title: "título", equipment_name: "equipo", equipment_type: "tipo de equipo",
  description: "descripción", priority: "prioridad", assigned_technician: "técnico", estimated_minutes: "duración",
};
const REQUEST_TIMEOUT_MS = 8000;

const app = {
  state: null,
  tableTasks: null,
  view: "ring",
  editingTaskId: null,
  blockingTaskId: null,
  deletingTaskId: null,
  integrityStale: false,
  busy: false,
};

const $ = (selector, root = document) => root.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

function setConnection(state, label) {
  const element = $("#connection-status");
  element.dataset.state = state;
  $(".label", element).textContent = label;
}

class ApiRequestError extends Error {
  constructor(message, status, field) {
    super(message);
    this.status = status;
    this.field = field;
  }
}

async function api(method, path, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (error) {
    setConnection("offline", "Sin conexión con el servidor");
    throw new ApiRequestError("No se pudo conectar con el servidor. Verifica que python server.py esté en ejecución.", 0);
  } finally {
    clearTimeout(timer);
  }
  let payload;
  try {
    payload = await response.json();
  } catch {
    setConnection("offline", "Respuesta inválida");
    throw new ApiRequestError("El servidor devolvió una respuesta inválida.", response.status);
  }
  setConnection("online", "Servidor conectado");
  if (!response.ok || !payload.ok) {
    const error = payload.error || {};
    throw new ApiRequestError(error.message || "La operación no se pudo completar.", response.status, error.field);
  }
  return payload;
}

function toast(message, type = "info") {
  const element = document.createElement("div");
  element.className = `toast ${type}`;
  element.textContent = message;
  $("#toasts").appendChild(element);
  setTimeout(() => element.remove(), type === "error" ? 6000 : 3500);
}

async function withLoading(button, task) {
  if (app.busy) return null;
  app.busy = true;
  button?.classList.add("is-loading");
  try {
    return await task();
  } finally {
    app.busy = false;
    button?.classList.remove("is-loading");
  }
}

async function mutate(method, path, body, successMessage, button) {
  return withLoading(button, async () => {
    try {
      const payload = await api(method, path, body);
      applyState(payload.state, true);
      if (successMessage) toast(successMessage, "success");
      return payload;
    } catch (error) {
      toast(error.message, "error");
      throw error;
    }
  }).catch(() => null);
}

function applyState(state, changed) {
  app.state = state;
  if (changed && $("#integrity-result").dataset.ran === "true") app.integrityStale = true;
  render();
  if (hasFilters()) loadFilteredTasks();
}

function hasFilters() {
  return $("#filter-status").value !== "ALL" || $("#filter-priority").value !== "ALL";
}

async function loadFilteredTasks() {
  const params = new URLSearchParams({ status: $("#filter-status").value, priority: $("#filter-priority").value });
  try {
    const payload = await api("GET", `/api/tasks?${params}`);
    app.tableTasks = payload.data;
    app.state = payload.state;
    renderTable();
  } catch (error) {
    toast(error.message, "error");
  }
}

function taskById(taskId) {
  return app.state?.tasks.find((task) => task.task_id === taskId) || null;
}

function render() {
  renderKpis();
  renderViz();
  renderCurrent();
  renderIntegrityStaleness();
  renderTable();
}

function renderKpis() {
  const summary = app.state.summary;
  $("#kpi-total").textContent = summary.total;
  $("#kpi-pending").textContent = summary.pending;
  $("#kpi-in-progress").textContent = summary.in_progress;
  $("#kpi-completed").textContent = summary.completed;
  $("#kpi-blocked").textContent = summary.blocked;
  $("#kpi-high").textContent = summary.high_priority;
}

function statusPill(status) {
  return `<span class="pill status-${status}"><span class="d"></span>${STATUS_LABELS[status]}</span>`;
}

function priorityPill(priority) {
  return `<span class="pill priority-${priority}">${PRIORITY_LABELS[priority]}</span>`;
}

function emptyStateMarkup() {
  return `
    <div class="empty-state">
      <div class="empty-ring">head = None</div>
      <strong>La ronda está vacía</strong>
      <span class="muted">size = 0 · current = None. Crea una tarea o carga los datos de demostración.</span>
      <div class="actions">
        <button class="btn primary" type="button" data-action="new">Nueva tarea</button>
        <button class="btn ghost" type="button" data-action="demo">Cargar demo</button>
      </div>
    </div>`;
}

function nodeMarkup(link) {
  const task = taskById(link.task_id);
  const prev = taskById(link.prev_task_id);
  const next = taskById(link.next_task_id);
  const tags = [link.is_head ? '<span class="tag head">HEAD</span>' : "", link.is_tail ? '<span class="tag tail">TAIL</span>' : ""].join("");
  return `
    <button type="button" class="node ${link.is_current ? "is-current" : ""}" data-select="${escapeHtml(task.task_id)}"
      aria-label="Nodo ${link.position + 1}: ${escapeHtml(task.title)}${link.is_current ? " (actual)" : ""}"
      title="prev: ${escapeHtml(prev.title)}\nnext: ${escapeHtml(next.title)}">
      <div class="node-top"><span class="node-id">${escapeHtml(task.task_id)}</span><span class="node-tags">${tags}</span></div>
      <div class="node-title">${escapeHtml(task.title)}</div>
      <div class="node-links"><span>← ${escapeHtml(link.prev_task_id)}</span><span class="n">${escapeHtml(link.next_task_id)} →</span></div>
      <div class="status-bar ${task.status}"></div>
    </button>`;
}

function renderViz() {
  const viz = $("#viz");
  const links = app.state.links;
  const ringAvailable = viz.clientWidth >= 640;
  const view = ringAvailable ? app.view : "linear";
  viz.classList.toggle("linear-mode", view === "linear" || links.length === 0);
  document.querySelectorAll(".seg").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
    button.disabled = !ringAvailable && button.dataset.view === "ring";
  });
  const hasTasks = links.length > 0;
  $("#btn-prev-ring").disabled = !hasTasks;
  $("#btn-next-ring").disabled = !hasTasks;
  if (!hasTasks) {
    viz.innerHTML = emptyStateMarkup();
    return;
  }
  if (view === "linear") renderLinear(viz, links);
  else renderRing(viz, links);
}

function renderLinear(viz, links) {
  const parts = [];
  links.forEach((link, index) => {
    parts.push(nodeMarkup(link));
    if (index < links.length - 1) {
      parts.push('<div class="link-pair" aria-hidden="true"><span class="a-next">next →</span><span class="a-prev">← prev</span></div>');
    }
  });
  const head = links[0];
  const tail = links[links.length - 1];
  viz.innerHTML = `
    <div class="linear-track">${parts.join("")}</div>
    <div class="wrap-back">
      <strong>Cierre circular:</strong>
      <span><code>tail.next</code> (${escapeHtml(tail.task_id)}) → <code>head</code> (${escapeHtml(tail.next_task_id)})</span>
      <span>·</span>
      <span><code>head.prev</code> (${escapeHtml(head.task_id)}) → <code>tail</code> (${escapeHtml(head.prev_task_id)})</span>
    </div>`;
}

function trimToCard(center, direction, halfWidth, halfHeight) {
  const tx = Math.abs(direction.x) > 1e-6 ? halfWidth / Math.abs(direction.x) : Infinity;
  const ty = Math.abs(direction.y) > 1e-6 ? halfHeight / Math.abs(direction.y) : Infinity;
  const t = Math.min(tx, ty);
  return { x: center.x + direction.x * t, y: center.y + direction.y * t };
}

function curvedLink(from, to, card, bend, offset) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.hypot(dx, dy) || 1;
  const direction = { x: dx / length, y: dy / length };
  const normal = { x: direction.y, y: -direction.x };
  const shift = (point) => ({ x: point.x + normal.x * offset, y: point.y + normal.y * offset });
  const start = shift(trimToCard(from, direction, card.halfWidth + 6, card.halfHeight + 6));
  const end = shift(trimToCard(to, { x: -direction.x, y: -direction.y }, card.halfWidth + 10, card.halfHeight + 10));
  const mid = { x: (start.x + end.x) / 2 + normal.x * bend, y: (start.y + end.y) / 2 + normal.y * bend };
  return { normal, d: `M ${start.x.toFixed(1)} ${start.y.toFixed(1)} Q ${mid.x.toFixed(1)} ${mid.y.toFixed(1)} ${end.x.toFixed(1)} ${end.y.toFixed(1)}`, mid };
}

function renderRing(viz, links) {
  const count = links.length;
  const compact = count > 8;
  const card = compact ? { width: 140, height: 76 } : { width: 168, height: 86 };
  card.halfWidth = card.width / 2;
  card.halfHeight = card.height / 2;
  const width = viz.clientWidth;
  const maxRadius = Math.min(340, Math.max(180, (width - card.width) / 2 - 30));
  const neededRadius = count > 1 ? (card.width + 34) / (2 * Math.sin(Math.PI / count)) : 0;
  const radius = Math.min(maxRadius, Math.max(210, neededRadius * 1.2));
  const height = Math.max(560, radius * 2 + card.height + 70);
  const center = { x: width / 2, y: height / 2 };
  const positions = links.map((_, index) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / count;
    return { x: center.x + radius * Math.cos(angle), y: center.y + radius * Math.sin(angle) };
  });
  const showLabels = count <= 6;
  const paths = [];
  if (count === 1) {
    const p = positions[0];
    const top = p.y - card.halfHeight - 6;
    paths.push(`<path class="link-next" marker-end="url(#arrow-next)" d="M ${p.x + 30} ${top} C ${p.x + 70} ${top - 70}, ${p.x - 70} ${top - 70}, ${p.x - 30} ${top}"/>`);
    paths.push(`<path class="link-prev" marker-end="url(#arrow-prev)" d="M ${p.x - 18} ${top} C ${p.x - 40} ${top - 40}, ${p.x + 40} ${top - 40}, ${p.x + 18} ${top}"/>`);
    if (showLabels) paths.push(`<text class="link-label" x="${p.x}" y="${top - 58}" text-anchor="middle">next = prev = self</text>`);
  } else {
    links.forEach((link, index) => {
      const nextIndex = (index + 1) % count;
      const isClosing = nextIndex === 0;
      const next = curvedLink(positions[index], positions[nextIndex], card, count === 2 ? 46 : 22, 7);
      const prev = curvedLink(positions[nextIndex], positions[index], card, count === 2 ? 46 : 22, 7);
      paths.push(`<path class="link-next${isClosing ? " closing" : ""}" marker-end="url(#arrow-next)" d="${next.d}"/>`);
      paths.push(`<path class="link-prev" marker-end="url(#arrow-prev)" d="${prev.d}"/>`);
      if (showLabels) {
        const nextLabel = { x: next.mid.x + next.normal.x * 16, y: next.mid.y + next.normal.y * 16 + 3 };
        const prevLabel = { x: prev.mid.x + prev.normal.x * 16, y: prev.mid.y + prev.normal.y * 16 + 3 };
        paths.push(`<text class="link-label" x="${nextLabel.x.toFixed(1)}" y="${nextLabel.y.toFixed(1)}" text-anchor="middle">${isClosing ? "next (tail→head)" : "next"}</text>`);
        paths.push(`<text class="link-label" x="${prevLabel.x.toFixed(1)}" y="${prevLabel.y.toFixed(1)}" text-anchor="middle">${isClosing ? "prev (head→tail)" : "prev"}</text>`);
      }
    });
  }
  const coreSize = Math.max(110, Math.min(190, (radius - card.halfWidth) * 2 - 30));
  const current = taskById(app.state.current_task_id);
  const nodes = links.map((link, index) => nodeMarkup(link).replace(
    'class="node',
    `style="left:${positions[index].x.toFixed(1)}px;top:${positions[index].y.toFixed(1)}px;width:${card.width}px;height:${card.height}px" class="node`,
  ));
  viz.innerHTML = `
    <div class="ring-stage" style="height:${height}px">
      <svg class="ring-svg" viewBox="0 0 ${width} ${height}" aria-hidden="true">
        <defs>
          <marker id="arrow-next" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="#4c9dff"/></marker>
          <marker id="arrow-prev" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="#8fa3bd"/></marker>
        </defs>
        <circle class="orbit" cx="${center.x}" cy="${center.y}" r="${radius}"/>
        ${paths.join("")}
      </svg>
      <div class="core" style="width:${coreSize}px;height:${coreSize}px;left:${center.x}px;top:${center.y}px">
        <div>
          <div class="core-label">Nodos activos</div>
          <div class="core-value">${count}</div>
          <div class="core-sub">current: ${escapeHtml(current ? current.task_id : "None")}</div>
        </div>
      </div>
      ${nodes.join("")}
    </div>`;
}

function renderCurrent() {
  const container = $("#current-task");
  const current = taskById(app.state.current_task_id);
  const link = app.state.links.find((item) => item.is_current);
  $("#current-position").textContent = link ? `Nodo ${link.position + 1} de ${app.state.links.length}` : "current = None";
  if (!current) {
    container.innerHTML = `<p class="empty-note">No hay una tarea seleccionada porque la ronda está vacía.</p>
      <div class="action-grid" style="margin-top:14px">
        <button class="btn primary" type="button" data-action="new">Nueva tarea</button>
        <button class="btn ghost" type="button" data-action="demo">Cargar demo</button>
      </div>`;
    return;
  }
  const prev = taskById(link.prev_task_id);
  const next = taskById(link.next_task_id);
  const id = escapeHtml(current.task_id);
  container.innerHTML = `
    <article class="current-card">
      <div class="eyebrow">${escapeHtml(EQUIPMENT_LABELS[current.equipment_type])} · <span class="source ${current.source}">${SOURCE_LABELS[current.source]}</span> · <span class="mono">${id}</span></div>
      <h3>${escapeHtml(current.title)}</h3>
      <p class="equip">${escapeHtml(current.equipment_name)}</p>
      <div class="pills">${statusPill(current.status)}${priorityPill(current.priority)}</div>
      <p class="desc">${escapeHtml(current.description)}</p>
      ${current.status === "BLOCKED" ? `<div class="block-reason"><strong>Motivo del bloqueo:</strong> ${escapeHtml(current.block_reason)}</div>` : ""}
      <div class="facts">
        <div class="fact"><span>Técnico asignado</span><strong>${escapeHtml(current.assigned_technician)}</strong></div>
        <div class="fact"><span>Duración estimada</span><strong>${current.estimated_minutes} min</strong></div>
      </div>
      <div class="links-box">
        <div><span class="k">current.prev</span><span class="v">${escapeHtml(prev.title)}</span></div>
        <div class="self">⇄</div>
        <div><span class="k">current.next</span><span class="v">${escapeHtml(next.title)}</span></div>
      </div>
      <div class="action-grid">
        <button class="btn" type="button" data-action="previous">← Retroceder</button>
        <button class="btn" type="button" data-action="next">Avanzar →</button>
        <button class="btn primary" type="button" data-action="start" data-id="${id}" ${current.status === "PENDING" ? "" : "disabled"}>Iniciar</button>
        <button class="btn" type="button" data-action="complete" data-id="${id}" ${current.status === "IN_PROGRESS" ? "" : "disabled"}>Completar</button>
        ${current.status === "BLOCKED"
          ? `<button class="btn" type="button" data-action="unblock" data-id="${id}">Resolver bloqueo</button>`
          : `<button class="btn danger" type="button" data-action="block" data-id="${id}" ${current.status === "COMPLETED" ? "disabled" : ""}>Bloquear</button>`}
        <button class="btn ghost" type="button" data-action="edit" data-id="${id}">Editar</button>
      </div>
    </article>`;
}

function renderTable() {
  const tbody = $("#task-rows");
  const tasks = hasFilters() && app.tableTasks ? app.tableTasks : app.state.tasks;
  const positions = new Map(app.state.links.map((link) => [link.task_id, link.position + 1]));
  if (!app.state.tasks.length) {
    tbody.innerHTML = '<tr><td colspan="10" class="table-empty">No hay tareas registradas en la ronda.</td></tr>';
    return;
  }
  if (!tasks.length) {
    tbody.innerHTML = '<tr><td colspan="10" class="table-empty">Ninguna tarea coincide con los filtros seleccionados.</td></tr>';
    return;
  }
  tbody.innerHTML = tasks.map((task) => {
    const id = escapeHtml(task.task_id);
    const isCurrent = task.task_id === app.state.current_task_id;
    return `
      <tr class="${isCurrent ? "is-current" : ""}">
        <td class="mono">${positions.get(task.task_id) ?? "—"}</td>
        <td class="mono">${id}</td>
        <td><strong>${escapeHtml(task.title)}</strong></td>
        <td>${escapeHtml(task.equipment_name)}<div class="muted">${escapeHtml(EQUIPMENT_LABELS[task.equipment_type])}</div></td>
        <td>${priorityPill(task.priority)}</td>
        <td>${statusPill(task.status)}</td>
        <td>${escapeHtml(task.assigned_technician)}</td>
        <td class="mono">${task.estimated_minutes}</td>
        <td><span class="source ${task.source}">${SOURCE_LABELS[task.source]}</span></td>
        <td class="right">
          <span class="row-actions">
            <button class="icon-btn" type="button" data-action="details" data-id="${id}" title="Ver detalle" aria-label="Ver detalle de ${id}">
              <svg viewBox="0 0 20 20"><path d="M2 10s3-6 8-6 8 6 8 6-3 6-8 6-8-6-8-6z" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="10" cy="10" r="2.5" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>
            </button>
            <button class="icon-btn" type="button" data-select="${id}" title="Seleccionar como actual" aria-label="Seleccionar ${id} como actual" ${isCurrent ? "disabled" : ""}>
              <svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="6.5" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="10" cy="10" r="2" fill="currentColor"/></svg>
            </button>
            <button class="icon-btn" type="button" data-action="edit" data-id="${id}" title="Editar" aria-label="Editar ${id}">
              <svg viewBox="0 0 20 20"><path d="M4 16l1-4 8-8 3 3-8 8z" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>
            </button>
            <button class="icon-btn danger" type="button" data-action="delete" data-id="${id}" title="Eliminar" aria-label="Eliminar ${id}">
              <svg viewBox="0 0 20 20"><path d="M5 6h10M8 6V4h4v2M6 6l1 10h6l1-10" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>
            </button>
          </span>
        </td>
      </tr>`;
  }).join("");
}

function renderIntegrityStaleness() {
  const note = $("#integrity-stale");
  if (note) note.hidden = !app.integrityStale;
}

async function runIntegrity(button) {
  await withLoading(button, async () => {
    try {
      const payload = await api("GET", "/api/integrity");
      app.state = payload.state;
      app.integrityStale = false;
      renderIntegrity(payload.data);
      render();
      toast(payload.data.valid ? "Integridad verificada: todos los enlaces son correctos." : "La verificación encontró enlaces inconsistentes.", payload.data.valid ? "success" : "error");
    } catch (error) {
      toast(error.message, "error");
    }
  });
}

function renderIntegrity(report) {
  const container = $("#integrity-result");
  container.dataset.ran = "true";
  const time = new Date().toLocaleTimeString("es-CO");
  container.innerHTML = `
    <div class="integrity-summary ${report.valid ? "ok" : "fail"}">
      <div class="integrity-icon">${report.valid ? "✓" : "!"}</div>
      <div>
        <strong>${report.valid ? "Estructura íntegra" : "Se detectaron inconsistencias"}</strong>
        <small>head: ${escapeHtml(report.head_task_id ?? "None")} · tail: ${escapeHtml(report.tail_task_id ?? "None")} · current: ${escapeHtml(report.current_task_id ?? "None")}</small>
      </div>
    </div>
    <div class="integrity-stats">
      <div class="fact"><span>size</span><strong>${report.size}</strong></div>
      <div class="fact"><span>Visitados con next</span><strong>${report.visited_forward}</strong></div>
      <div class="fact"><span>Visitados con prev</span><strong>${report.visited_backward}</strong></div>
    </div>
    <ul class="check-list">
      ${report.checks.map((check) => `<li><span>${escapeHtml(CHECK_LABELS[check.name] || check.name)}</span><span class="${check.passed ? "pass" : "failx"}">${check.passed ? "OK" : "FALLA"}</span></li>`).join("")}
    </ul>
    <p class="integrity-time">Ejecutado por el backend a las ${time}.</p>
    <p class="integrity-time" id="integrity-stale" hidden>La ronda cambió después de esta verificación. Ejecútala de nuevo para comprobar el estado actual.</p>`;
}

function fillAfterOptions(selectedId) {
  const select = $('select[name="after_task_id"]');
  select.innerHTML = app.state.tasks.map((task) => `<option value="${escapeHtml(task.task_id)}">${escapeHtml(task.task_id)} — ${escapeHtml(task.title)}</option>`).join("");
  if (selectedId) select.value = selectedId;
}

function openTaskDialog(taskId) {
  const form = $("#task-form");
  form.reset();
  clearFormErrors(form);
  app.editingTaskId = taskId || null;
  const task = taskId ? taskById(taskId) : null;
  $("#task-dialog-title").textContent = task ? `Editar ${task.task_id}` : "Nueva tarea";
  form.task_id.disabled = Boolean(task);
  form.querySelectorAll(".insert-only").forEach((field) => { field.hidden = Boolean(task); });
  if (task) {
    for (const name of Object.keys(FIELD_LABELS)) form[name].value = task[name];
  } else {
    fillAfterOptions(app.state.current_task_id);
    form.position.disabled = app.state.tasks.length === 0;
    $("#after-field").hidden = true;
  }
  $("#task-dialog").showModal();
  (task ? form.elements.title : form.task_id).focus();
}

function clearFormErrors(form) {
  form.querySelectorAll("[aria-invalid]").forEach((field) => field.removeAttribute("aria-invalid"));
  form.querySelector(".form-error").textContent = "";
}

function clientValidationMessage(field) {
  const label = FIELD_LABELS[field.name] || field.name;
  const validity = field.validity;
  if (validity.valueMissing) return `El campo ${label} es obligatorio.`;
  if (validity.tooShort) return `El campo ${label} debe tener al menos ${field.minLength} caracteres.`;
  if (validity.rangeUnderflow || validity.rangeOverflow) return `La duración debe estar entre ${field.min} y ${field.max} minutos.`;
  if (validity.stepMismatch || validity.badInput) return "La duración debe ser un número entero.";
  if (validity.patternMismatch) return "El identificador solo admite letras, números y guiones (máx. 20).";
  return `Revisa el campo ${label}.`;
}

function validateForm(form) {
  clearFormErrors(form);
  for (const field of form.elements) {
    if (!field.name || field.disabled || field.closest("[hidden]")) continue;
    if (field.type !== "number" && typeof field.value === "string" && field.required && !field.value.trim()) {
      field.value = "";
    }
    if (!field.checkValidity()) {
      field.setAttribute("aria-invalid", "true");
      form.querySelector(".form-error").textContent = clientValidationMessage(field);
      field.focus();
      return false;
    }
  }
  return true;
}

function showServerFieldError(form, error) {
  form.querySelector(".form-error").textContent = error.message;
  if (error.field && form[error.field]) {
    form[error.field].setAttribute("aria-invalid", "true");
    form[error.field].focus();
  }
}

async function submitTaskForm(event) {
  event.preventDefault();
  const form = event.target;
  if (!validateForm(form)) return;
  const task = {
    title: form.elements.title.value.trim(),
    equipment_name: form.equipment_name.value.trim(),
    equipment_type: form.equipment_type.value,
    description: form.description.value.trim(),
    priority: form.priority.value,
    assigned_technician: form.assigned_technician.value.trim(),
    estimated_minutes: Number(form.estimated_minutes.value),
  };
  const button = $("#task-submit");
  await withLoading(button, async () => {
    try {
      let payload;
      if (app.editingTaskId) {
        payload = await api("PUT", `/api/tasks/${encodeURIComponent(app.editingTaskId)}`, task);
        toast(`Tarea ${app.editingTaskId} actualizada.`, "success");
      } else {
        const body = { task: { ...task, task_id: form.task_id.value.trim() || null }, position: form.position.value };
        if (body.position === "after") body.after_task_id = form.after_task_id.value;
        payload = await api("POST", "/api/tasks", body);
        toast(`Tarea ${payload.data.task_id} insertada en la ronda.`, "success");
      }
      $("#task-dialog").close();
      applyState(payload.state, true);
    } catch (error) {
      showServerFieldError(form, error);
    }
  });
}

function openBlockDialog(taskId) {
  const task = taskById(taskId);
  if (!task) return;
  app.blockingTaskId = taskId;
  const form = $("#block-form");
  form.reset();
  clearFormErrors(form);
  $("#block-task-name").textContent = `${task.task_id} — ${task.title}`;
  $("#block-dialog").showModal();
  form.reason.focus();
}

async function submitBlockForm(event) {
  event.preventDefault();
  const form = event.target;
  if (!validateForm(form)) {
    form.querySelector(".form-error").textContent = "El motivo debe tener entre 5 y 200 caracteres.";
    return;
  }
  await withLoading(form.querySelector('button[type="submit"]'), async () => {
    try {
      const payload = await api("POST", `/api/tasks/${encodeURIComponent(app.blockingTaskId)}/block`, { reason: form.reason.value.trim() });
      $("#block-dialog").close();
      applyState(payload.state, true);
      toast(`Tarea ${app.blockingTaskId} bloqueada.`, "success");
    } catch (error) {
      showServerFieldError(form, error);
    }
  });
}

function openDeleteDialog(taskId) {
  const task = taskById(taskId);
  if (!task) return;
  app.deletingTaskId = taskId;
  $("#confirm-message").innerHTML = `¿Eliminar <strong>${escapeHtml(task.title)}</strong> (${escapeHtml(task.task_id)}) de la ronda?`;
  $("#confirm-dialog").showModal();
}

function openDetails(taskId) {
  const task = taskById(taskId);
  if (!task) return;
  const link = app.state.links.find((item) => item.task_id === taskId);
  const rows = [
    ["Identificador", task.task_id],
    ["Título", task.title],
    ["Equipo", task.equipment_name],
    ["Tipo de equipo", EQUIPMENT_LABELS[task.equipment_type]],
    ["Descripción", task.description],
    ["Prioridad", PRIORITY_LABELS[task.priority]],
    ["Estado", STATUS_LABELS[task.status]],
    ["Técnico", task.assigned_technician],
    ["Duración", `${task.estimated_minutes} min`],
    ["Origen", task.source === "DEMO" ? "Dato de demostración" : "Registrada por el usuario"],
    ["Posición", `${link.position + 1} de ${app.state.links.length}`],
    ["node.prev", link.prev_task_id],
    ["node.next", link.next_task_id],
  ];
  if (task.status === "BLOCKED") rows.push(["Motivo del bloqueo", task.block_reason]);
  $("#details-body").innerHTML = `<dl class="details-list">${rows.map(([key, value]) => `<dt>${key}</dt><dd>${escapeHtml(value)}</dd>`).join("")}</dl>`;
  $("#details-dialog").showModal();
}

async function handleAction(button) {
  const action = button.dataset.action;
  const id = button.dataset.id;
  const encoded = encodeURIComponent(id || "");
  switch (action) {
    case "new": return openTaskDialog();
    case "demo": return loadDemo(button);
    case "next": return mutate("POST", "/api/navigation/next", null, null, button);
    case "previous": return mutate("POST", "/api/navigation/previous", null, null, button);
    case "start": return mutate("POST", `/api/tasks/${encoded}/start`, null, `Tarea ${id} en ejecución.`, button);
    case "complete": return mutate("POST", `/api/tasks/${encoded}/complete`, null, `Tarea ${id} completada.`, button);
    case "unblock": return mutate("POST", `/api/tasks/${encoded}/unblock`, null, `Bloqueo de ${id} resuelto. La tarea vuelve a Pendiente.`, button);
    case "block": return openBlockDialog(id);
    case "edit": return openTaskDialog(id);
    case "delete": return openDeleteDialog(id);
    case "details": return openDetails(id);
    default: return null;
  }
}

async function loadDemo(button) {
  const payload = await mutate("POST", "/api/demo", null, null, button);
  if (!payload) return;
  toast(payload.data.length ? `Se cargaron ${payload.data.length} tareas de demostración.` : "Las tareas de demostración ya estaban cargadas; no se duplicaron.", "success");
}

function bindEvents() {
  document.addEventListener("click", (event) => {
    const closeButton = event.target.closest("[data-close]");
    if (closeButton) {
      closeButton.closest("dialog").close();
      return;
    }
    const selectButton = event.target.closest("[data-select]");
    if (selectButton) {
      const id = selectButton.dataset.select;
      if (id !== app.state.current_task_id) mutate("POST", `/api/tasks/${encodeURIComponent(id)}/select`, null, null, null);
      return;
    }
    const actionButton = event.target.closest("[data-action]");
    if (actionButton && !actionButton.disabled) handleAction(actionButton);
  });

  $("#btn-new-task").addEventListener("click", () => app.state && openTaskDialog());
  $("#btn-demo").addEventListener("click", (event) => loadDemo(event.currentTarget));
  $("#btn-integrity").addEventListener("click", (event) => runIntegrity(event.currentTarget));
  $("#btn-integrity-2").addEventListener("click", (event) => runIntegrity(event.currentTarget));
  $("#btn-next-ring").addEventListener("click", (event) => mutate("POST", "/api/navigation/next", null, null, event.currentTarget));
  $("#btn-prev-ring").addEventListener("click", (event) => mutate("POST", "/api/navigation/previous", null, null, event.currentTarget));

  document.querySelectorAll(".seg").forEach((button) => button.addEventListener("click", () => {
    app.view = button.dataset.view;
    if (app.state) renderViz();
  }));

  $("#filter-status").addEventListener("change", onFilterChange);
  $("#filter-priority").addEventListener("change", onFilterChange);

  $("#task-form").addEventListener("submit", submitTaskForm);
  $("#task-form").position.addEventListener("change", (event) => {
    $("#after-field").hidden = event.target.value !== "after";
  });
  $("#block-form").addEventListener("submit", submitBlockForm);
  $("#confirm-delete").addEventListener("click", async (event) => {
    const id = app.deletingTaskId;
    const payload = await mutate("DELETE", `/api/tasks/${encodeURIComponent(id)}`, null, `Tarea ${id} eliminada. Los nodos vecinos quedaron enlazados.`, event.currentTarget);
    if (payload) $("#confirm-dialog").close();
  });

  document.addEventListener("keydown", (event) => {
    if (!app.state || !app.state.tasks.length || document.querySelector("dialog[open]")) return;
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
    if (event.key === "ArrowRight") mutate("POST", "/api/navigation/next", null, null, null);
    if (event.key === "ArrowLeft") mutate("POST", "/api/navigation/previous", null, null, null);
  });

  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => app.state && renderViz(), 150);
  });
}

function onFilterChange() {
  if (!app.state) return;
  if (hasFilters()) loadFilteredTasks();
  else {
    app.tableTasks = null;
    renderTable();
  }
}

async function initialize() {
  bindEvents();
  try {
    const payload = await api("GET", "/api/state");
    applyState(payload.state, false);
  } catch (error) {
    $("#viz").innerHTML = `<div class="empty-state"><strong>No se pudo cargar la ronda</strong><span class="muted">${escapeHtml(error.message)}</span><div class="actions"><button class="btn primary" type="button" id="btn-retry">Reintentar</button></div></div>`;
    $("#current-task").innerHTML = '<p class="empty-note">Sin datos del servidor.</p>';
    $("#task-rows").innerHTML = '<tr><td colspan="10" class="table-empty">Sin conexión con el servidor.</td></tr>';
    $("#btn-retry").addEventListener("click", () => window.location.reload());
  }
}

initialize();
