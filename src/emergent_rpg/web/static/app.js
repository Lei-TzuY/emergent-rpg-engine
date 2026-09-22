const ui = {
  shell: document.querySelector("#app-shell"),
  connection: document.querySelector("#connection-state"),
  error: document.querySelector("#error-banner"),
  sessionId: document.querySelector("#session-id"),
  newSession: document.querySelector("#new-session"),
  loadSession: document.querySelector("#load-session"),
  location: document.querySelector("#location-name"),
  worldTime: document.querySelector("#world-time"),
  vitals: document.querySelector("#player-vitals"),
  conditions: document.querySelector("#location-conditions"),
  exits: document.querySelector("#exits"),
  blockedExits: document.querySelector("#blocked-exits"),
  items: document.querySelector("#visible-items"),
  npcs: document.querySelector("#visible-npcs"),
  inventory: document.querySelector("#inventory"),
  facts: document.querySelector("#known-facts"),
  activeObjectives: document.querySelector("#active-objectives"),
  completedObjectives: document.querySelector("#completed-objectives"),
  failedObjectives: document.querySelector("#failed-objectives"),
  turnCounter: document.querySelector("#turn-counter"),
  history: document.querySelector("#history-log"),
  actionForm: document.querySelector("#action-form"),
  actionInput: document.querySelector("#action-input"),
  sendAction: document.querySelector("#send-action"),
};

const state = {
  sessionId: localStorage.getItem("emergent-rpg-session") || "",
  busy: false,
};

function setBusy(busy, message = "Working…") {
  state.busy = busy;
  ui.shell.setAttribute("aria-busy", String(busy));
  ui.connection.textContent = busy ? message : state.sessionId ? "Connected" : "Idle";
  ui.newSession.disabled = busy;
  ui.loadSession.disabled = busy;
  ui.sendAction.disabled = busy || !state.sessionId;
  ui.actionInput.disabled = busy || !state.sessionId;
}

function showError(message) {
  ui.error.textContent = message;
  ui.error.hidden = false;
}

function clearError() {
  ui.error.textContent = "";
  ui.error.hidden = true;
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return payload;
}

function setSessionId(sessionId) {
  state.sessionId = sessionId;
  ui.sessionId.value = sessionId;
  if (sessionId) {
    localStorage.setItem("emergent-rpg-session", sessionId);
  } else {
    localStorage.removeItem("emergent-rpg-session");
  }
}

function renderChips(container, values, fallback = "—") {
  container.replaceChildren();
  if (!values.length) {
    const empty = document.createElement("span");
    empty.className = "muted";
    empty.textContent = fallback;
    container.append(empty);
    return;
  }
  values.forEach((value) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = value;
    container.append(chip);
  });
}

function renderConditions(conditions) {
  ui.conditions.replaceChildren();
  if (!conditions.length) {
    const empty = document.createElement("li");
    empty.className = "muted";
    empty.textContent = "none";
    ui.conditions.append(empty);
    return;
  }
  conditions.forEach((condition) => {
    const item = document.createElement("li");
    const traversal = condition.traversal_extra_minutes > 0
      ? ` Travel +${condition.traversal_extra_minutes} min.`
      : "";
    item.textContent = `${condition.name}: ${condition.description}${traversal}`;
    ui.conditions.append(item);
  });
}

function renderObjectives(container, objectives) {
  container.replaceChildren();
  if (!objectives.length) {
    const empty = document.createElement("li");
    empty.className = "muted";
    empty.textContent = "none";
    container.append(empty);
    return;
  }
  objectives.forEach((objective) => {
    const item = document.createElement("li");
    const deadline = objective.deadline ? ` · due ${objective.deadline}` : "";
    item.textContent = `${objective.title}: ${objective.description}${deadline}`;
    container.append(item);
  });
}

function renderState(view) {
  ui.location.textContent = view.location_name;
  ui.worldTime.textContent = `${view.time} · Turn ${view.turn_number}`;
  ui.turnCounter.textContent = `Turn ${view.turn_number}`;
  renderChips(ui.vitals, [
    `Health ${view.health}/10`,
    `Stamina ${view.stamina}/10`,
    `Weapon ${view.equipped_weapon ? view.equipped_weapon.name : "unarmed"}`,
  ]);
  renderConditions(view.location_conditions || []);
  renderChips(ui.exits, Object.entries(view.exits).map(([alias, name]) => `${alias} → ${name}`));
  renderChips(
    ui.blockedExits,
    (view.blocked_exits || []).map((exit) => {
      const blockers = exit.blocked_by.join(", ");
      return `${exit.alias} → ${exit.destination_name} · blocked by ${blockers}`;
    }),
    "none",
  );
  renderChips(ui.items, view.visible_items.map((item) => item.name), "nothing portable");
  renderChips(ui.npcs, view.visible_npcs.map((npc) => npc.name), "none");
  renderChips(ui.inventory, view.inventory.map((item) => item.name), "empty");
  renderObjectives(ui.activeObjectives, view.active_objectives || []);
  renderObjectives(ui.completedObjectives, view.completed_objectives || []);
  renderObjectives(ui.failedObjectives, view.failed_objectives || []);

  ui.facts.replaceChildren();
  if (!view.known_facts.length) {
    const empty = document.createElement("li");
    empty.className = "muted";
    empty.textContent = "none yet";
    ui.facts.append(empty);
  } else {
    view.known_facts.forEach((fact) => {
      const item = document.createElement("li");
      item.textContent = fact.proposition;
      ui.facts.append(item);
    });
  }
}

function renderHistory(turns) {
  ui.history.replaceChildren();
  if (!turns.length) {
    const empty = document.createElement("li");
    empty.className = "empty-history";
    empty.textContent = "No turns yet. The relay is waiting.";
    ui.history.append(empty);
    return;
  }
  turns.forEach((turn) => {
    const item = document.createElement("li");
    item.className = `history-entry ${turn.accepted ? "accepted" : "rejected"}`;

    const meta = document.createElement("div");
    meta.className = "history-meta";
    meta.textContent = `T${String(turn.turn_number).padStart(3, "0")} · ${turn.accepted ? "accepted" : "rejected"}`;

    const command = document.createElement("p");
    command.className = "history-command";
    command.textContent = `> ${turn.raw_input}`;

    const narration = document.createElement("p");
    narration.className = "history-narration";
    narration.textContent = turn.narration;

    item.append(meta, command, narration);
    ui.history.append(item);
  });
  ui.history.lastElementChild?.scrollIntoView({ block: "nearest" });
}

async function refreshHistory() {
  if (!state.sessionId) return;
  const payload = await request(`/sessions/${encodeURIComponent(state.sessionId)}/history?limit=100`);
  renderHistory(payload.turns);
}

async function loadSession(sessionId) {
  clearError();
  setBusy(true, "Loading…");
  try {
    const payload = await request(`/sessions/${encodeURIComponent(sessionId)}`);
    setSessionId(payload.session.id);
    renderState(payload.state);
    await refreshHistory();
  } catch (error) {
    showError(error instanceof Error ? error.message : "Unable to load session.");
  } finally {
    setBusy(false);
  }
}

async function createSession() {
  clearError();
  setBusy(true, "Creating…");
  try {
    const payload = await request("/sessions", {
      method: "POST",
      body: JSON.stringify({ name: "Ashfall Relay" }),
    });
    setSessionId(payload.session.id);
    renderState(payload.state);
    renderHistory([]);
    ui.actionInput.focus();
  } catch (error) {
    showError(error instanceof Error ? error.message : "Unable to create session.");
  } finally {
    setBusy(false);
  }
}

async function submitAction(event) {
  event.preventDefault();
  const text = ui.actionInput.value.trim();
  if (!state.sessionId || !text || state.busy) return;

  clearError();
  setBusy(true, "Resolving…");
  try {
    const payload = await request(
      `/sessions/${encodeURIComponent(state.sessionId)}/actions`,
      { method: "POST", body: JSON.stringify({ text }) },
    );
    renderState(payload.state);
    ui.actionInput.value = "";
    await refreshHistory();
    if (!payload.accepted && payload.reason) {
      showError(`Action rejected: ${payload.reason}`);
    }
  } catch (error) {
    showError(error instanceof Error ? error.message : "Action failed.");
  } finally {
    setBusy(false);
    ui.actionInput.focus();
  }
}

ui.newSession.addEventListener("click", createSession);
ui.loadSession.addEventListener("click", () => {
  const sessionId = ui.sessionId.value.trim();
  if (sessionId) loadSession(sessionId);
});
ui.actionForm.addEventListener("submit", submitAction);

ui.sessionId.value = state.sessionId;
setBusy(false);
if (state.sessionId) {
  loadSession(state.sessionId);
}
