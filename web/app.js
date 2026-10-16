import {
  FORMATIONS, STORAGE_KEY, createInitialState, validateTactic,
  serializeTactic, deserializeTactic, resolveTeam, eligiblePlayers,
  setTeam, setKit, setFormation, setPlayer, movePlayer, toggleSubstitution,
  resetPositions, addArrow, setBall, clearAnnotations,
  createHistory, commit, undo,
} from "./state.js";
import { renderBoard } from "./board-svg.js";

const pitch = document.querySelector("#pitch");
const status = document.querySelector("#status");
const playerDialog = document.querySelector("#player-dialog");
const playerChoice = document.querySelector("#player-choice");
const jsonFile = document.querySelector("#json-file");
const modeButtons = [...document.querySelectorAll("[data-mode]")];

let teams = [];
let history;
let state;
let mode = "move";
let pointer = null;
let dialogSlot = null;
const importedTeams = new Map();

function announce(message) {
  status.textContent = message;
}

function displayError(error) {
  announce(error instanceof Error ? error.message : String(error));
}

function rememberImportedTeams() {
  for (const side of state.sides) {
    if (side.team_data) importedTeams.set(side.team_id, side.team_data);
  }
}

function availableTeams() {
  return [...teams, ...importedTeams.values()];
}

function option(value, label) {
  const entry = document.createElement("option");
  entry.value = String(value);
  entry.textContent = label;
  return entry;
}

function setOptions(select, choices, selected) {
  select.replaceChildren(...choices.map(([value, label]) => option(value, label)));
  select.value = String(selected);
}

function renderControls() {
  rememberImportedTeams();
  const teamOptions = availableTeams().map(team => [team.id, team.name]);
  for (const side of [0, 1]) {
    const saved = state.sides[side];
    const team = resolveTeam(state, teams, side);
    setOptions(document.querySelector(`#team-${side}`), teamOptions, saved.team_id);
    setOptions(document.querySelector(`#kit-${side}`),
      team.kits.map((kit, index) => [index, kit.name]), saved.kit_index);
    setOptions(document.querySelector(`#formation-${side}`),
      Object.keys(FORMATIONS).map(name => [name, name]), saved.formation);
  }
  modeButtons.forEach(button => {
    button.setAttribute("aria-pressed", String(button.dataset.mode === mode));
  });
  document.querySelector("#undo").disabled = history.past.length === 0;
  document.querySelector("#board-hint").textContent = {
    move: "Drag a player to move them. Select a player to change them. Use the gold switch badge for a match substitution.",
    arrow: "Drag across the pitch to draw an arrow.",
    ball: "Tap or drag on the pitch to place the ball.",
  }[mode];
}

function render(draftArrow = null) {
  renderControls();
  renderBoard(pitch, state, teams, { mode, draftArrow });
}

function renderPitch(draftArrow = null) {
  renderBoard(pitch, state, teams, { mode, draftArrow });
}

function change(next, message) {
  if (JSON.stringify(next) === JSON.stringify(history.present)) return;
  history = commit(history, validateTactic(next, teams));
  state = history.present;
  render();
  if (message) announce(message);
}

function run(action) {
  try { action(); }
  catch (error) { displayError(error); }
}

function svgPoint(event) {
  const matrix = pitch.getScreenCTM();
  if (!matrix) throw new Error("The pitch is not ready");
  const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
  return [Math.max(0, Math.min(105, point.x)), Math.max(0, Math.min(68, point.y))];
}

function tokenFromEvent(event) {
  const token = event.target instanceof Element ? event.target.closest("[data-player]") : null;
  if (!token) return null;
  return { side: Number(token.dataset.side), slot: Number(token.dataset.slot), element: token };
}

function finishPointer(event, cancelled = false) {
  if (!pointer || event.pointerId !== pointer.id) return;
  const active = pointer;
  pointer = null;
  try { pitch.releasePointerCapture(event.pointerId); } catch { /* capture may already be lost */ }
  if (cancelled) {
    state = history.present;
    renderPitch();
    return;
  }
  if (active.mode === "move") {
    if (active.moved) {
      change(state, `Moved ${state.sides[active.side].players[active.slot].name}`);
    } else {
      openPlayerDialog(active.side, active.slot);
    }
  } else if (active.mode === "arrow") {
    const end = svgPoint(event);
    const distance = Math.hypot(event.clientX - active.clientX, event.clientY - active.clientY);
    if (distance > 6) change(addArrow(history.present, active.start, end), "Arrow added");
    else renderPitch();
  } else if (active.mode === "ball") {
    change(state, "Ball placed");
  }
}

pitch.addEventListener("pointerdown", event => run(() => {
  if (event.button !== 0 || pointer) return;
  const token = tokenFromEvent(event);
  const badge = event.target instanceof Element ? event.target.closest("[data-switch]") : null;
  if (mode === "move" && badge && token) {
    const next = toggleSubstitution(history.present, token.side, token.slot);
    change(next, `Switched to ${next.sides[token.side].players[token.slot].name}`);
    return;
  }
  const start = svgPoint(event);
  if (mode === "move") {
    if (!token) return;
    pointer = { id: event.pointerId, mode, side: token.side, slot: token.slot,
      clientX: event.clientX, clientY: event.clientY, moved: false,
      offset: [state.sides[token.side].players[token.slot].x_m - start[0],
        state.sides[token.side].players[token.slot].y_m - start[1]] };
  } else {
    pointer = { id: event.pointerId, mode, start,
      clientX: event.clientX, clientY: event.clientY };
    if (mode === "ball") {
      state = setBall(history.present, start);
      renderPitch();
    }
  }
  pitch.setPointerCapture(event.pointerId);
  event.preventDefault();
}));

pitch.addEventListener("pointermove", event => run(() => {
  if (!pointer || pointer.id !== event.pointerId) return;
  const point = svgPoint(event);
  if (pointer.mode === "move") {
    const distance = Math.hypot(event.clientX - pointer.clientX, event.clientY - pointer.clientY);
    if (distance <= 6 && !pointer.moved) return;
    pointer.moved = true;
    state = movePlayer(history.present, pointer.side, pointer.slot,
      point[0] + pointer.offset[0], point[1] + pointer.offset[1]);
    renderPitch();
  } else if (pointer.mode === "arrow") {
    renderPitch([pointer.start, point]);
  } else if (pointer.mode === "ball") {
    state = setBall(history.present, point);
    renderPitch();
  }
}));
pitch.addEventListener("pointerup", event => run(() => finishPointer(event)));
pitch.addEventListener("pointercancel", event => finishPointer(event, true));

pitch.addEventListener("keydown", event => run(() => {
  const token = tokenFromEvent(event);
  if (!token) return;
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    if (event.target instanceof Element && event.target.closest("[data-switch]")) {
      const next = toggleSubstitution(history.present, token.side, token.slot);
      change(next, `Switched to ${next.sides[token.side].players[token.slot].name}`);
    } else {
      openPlayerDialog(token.side, token.slot);
    }
    return;
  }
  const steps = { ArrowLeft: [-1, 0], ArrowRight: [1, 0],
    ArrowUp: [0, -1], ArrowDown: [0, 1] };
  const direction = steps[event.key];
  if (!direction) return;
  event.preventDefault();
  const player = state.sides[token.side].players[token.slot];
  const step = event.shiftKey ? 2 : 0.5;
  change(movePlayer(history.present, token.side, token.slot,
    player.x_m + direction[0] * step, player.y_m + direction[1] * step),
  `Moved ${player.name}`);
  pitch.querySelector(`[data-player][data-side="${token.side}"][data-slot="${token.slot}"]`)?.focus({ preventScroll: true });
}));

function openPlayerDialog(side, slot) {
  dialogSlot = { side, slot };
  const current = state.sides[side].players[slot];
  const team = resolveTeam(state, teams, side);
  document.querySelector("#player-dialog-context").textContent =
    `${team.name} · #${current.number} ${current.name}`;
  const eligible = eligiblePlayers(state, teams, side, slot);
  playerChoice.replaceChildren(...eligible.map((player, index) =>
    option(index, `#${player.number} ${player.name} (${player.position})`)));
  playerChoice.value = String(Math.max(0, eligible.findIndex(player =>
    player.number === current.number && player.name === current.name)));
  playerChoice._eligible = eligible;
  const switchButton = document.querySelector("#dialog-switch");
  switchButton.hidden = !current.switch_pair;
  if (current.switch_pair) {
    const target = current.switch_pair[current.switch_active ? "before" : "after"];
    switchButton.textContent = `Switch to #${target.number} ${target.name}`;
  }
  playerDialog.showModal();
  playerChoice.focus();
}

document.querySelector("#dialog-choose").addEventListener("click", () => run(() => {
  if (!dialogSlot) return;
  const person = playerChoice._eligible?.[Number(playerChoice.value)];
  if (!person) return;
  const { side, slot } = dialogSlot;
  const current = state.sides[side].players[slot];
  if (current.name !== person.name || current.number !== person.number || current.position !== person.position) {
    change(setPlayer(history.present, teams, side, slot, person), `Selected ${person.name}`);
  }
  playerDialog.close();
}));

document.querySelector("#dialog-switch").addEventListener("click", () => run(() => {
  if (!dialogSlot) return;
  const { side, slot } = dialogSlot;
  const next = toggleSubstitution(history.present, side, slot);
  change(next, `Switched to ${next.sides[side].players[slot].name}`);
  playerDialog.close();
}));

for (const side of [0, 1]) {
  document.querySelector(`#team-${side}`).addEventListener("change", event => run(() => {
    const team = availableTeams().find(item => item.id === event.target.value);
    if (!team) throw new Error("Unknown team");
    change(setTeam(history.present, side, team), `${team.name} selected`);
  }));
  document.querySelector(`#kit-${side}`).addEventListener("change", event => run(() =>
    change(setKit(history.present, side, Number(event.target.value), teams), "Uniform changed")));
  document.querySelector(`#formation-${side}`).addEventListener("change", event => run(() =>
    change(setFormation(history.present, side, event.target.value), `Formation: ${event.target.value}`)));
}

modeButtons.forEach(button => button.addEventListener("click", () => {
  mode = button.dataset.mode;
  render();
  announce({ move: "Move players", arrow: "Draw arrows", ball: "Place ball" }[mode]);
}));
document.querySelector("#undo").addEventListener("click", () => {
  if (!history.past.length) return announce("Nothing to undo");
  history = undo(history);
  state = history.present;
  render();
  announce("Last change undone");
});
document.querySelector("#reset").addEventListener("click", () => run(() =>
  change(resetPositions(history.present), "Positions reset")));
document.querySelector("#clear").addEventListener("click", () => run(() =>
  change(clearAnnotations(history.present), "Arrows and ball cleared")));

function download(name, blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function save() {
  localStorage.setItem(STORAGE_KEY, serializeTactic(state, teams));
  announce("Tactic saved in this browser");
}
function load() {
  const text = localStorage.getItem(STORAGE_KEY);
  if (text == null) throw new Error("No saved tactic in this browser");
  change(deserializeTactic(text, teams), "Tactic loaded");
}
function exportJson() {
  download("tactic-export.json", new Blob([serializeTactic(state, teams)], { type: "application/json" }));
  announce("JSON exported");
}
async function exportPng() {
  const clone = pitch.cloneNode(true);
  clone.setAttribute("width", "2300");
  clone.setAttribute("height", "1560");
  const source = new XMLSerializer().serializeToString(clone);
  const svgUrl = URL.createObjectURL(new Blob([source], { type: "image/svg+xml;charset=utf-8" }));
  try {
    const image = new Image();
    image.src = svgUrl;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = 2300;
    canvas.height = 1560;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("PNG export is unavailable");
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/png"));
    if (!blob) throw new Error("PNG export failed");
    download("tactic.png", blob);
    announce("PNG exported");
  } finally {
    URL.revokeObjectURL(svgUrl);
  }
}

document.querySelector("#save").addEventListener("click", () => run(save));
document.querySelector("#load").addEventListener("click", () => run(load));
document.querySelector("#export-json").addEventListener("click", () => run(exportJson));
document.querySelector("#export-png").addEventListener("click", () => { exportPng().catch(displayError); });
document.querySelector("#import-json").addEventListener("click", () => jsonFile.click());
jsonFile.addEventListener("change", async () => {
  const file = jsonFile.files?.[0];
  if (!file) return;
  try {
    if (file.size > 1024 * 1024) throw new Error("Tactic exceeds the 1 MB limit");
    change(deserializeTactic(await file.text(), teams), "JSON tactic imported");
  } catch (error) { displayError(error); }
  finally { jsonFile.value = ""; }
});

document.querySelector("#match-form").addEventListener("submit", async event => {
  event.preventDefault();
  const url = document.querySelector("#match-url").value.trim();
  const submit = document.querySelector("#match-submit");
  submit.disabled = true;
  announce("Loading Zerozero match…");
  try {
    const endpoint = new URL("./api/match", document.baseURI);
    endpoint.searchParams.set("url", url);
    const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
    if (!response.headers.get("content-type")?.includes("application/json")) {
      throw new Error("Link import needs the hosted app or local server. This static site has no match import service.");
    }
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not import this match");
    if (!Array.isArray(result.teams) || result.teams.length !== 2) throw new Error("Match has no complete teams");
    let next = createInitialState(teams);
    next = setTeam(next, 0, result.teams[0]);
    next = setTeam(next, 1, result.teams[1]);
    change(next, `Imported ${result.teams[0].name} vs ${result.teams[1].name}`);
  } catch (error) { displayError(error); }
  finally { submit.disabled = false; }
});

document.addEventListener("keydown", event => {
  if (playerDialog.open || event.target instanceof HTMLInputElement ||
      event.target instanceof HTMLSelectElement) return;
  if (event.ctrlKey && !event.altKey) {
    const key = event.key.toLowerCase();
    if (key === "z") { event.preventDefault(); document.querySelector("#undo").click(); }
    else if (key === "s") { event.preventDefault(); run(save); }
    else if (key === "o") { event.preventDefault(); run(load); }
    else if (key === "e") { event.preventDefault(); exportPng().catch(displayError); }
  } else if (event.key.toLowerCase() === "r" && !(event.target instanceof HTMLButtonElement)) {
    event.preventDefault();
    run(() => change(resetPositions(history.present), "Positions reset"));
  }
});

window.addEventListener("resize", () => {
  if (state) renderPitch();
});

try {
  const response = await fetch("./teams.json");
  if (!response.ok) throw new Error("Could not load team data");
  teams = await response.json();
  state = createInitialState(teams);
  history = createHistory(state);
  render();
  announce("Board ready");
} catch (error) {
  displayError(error);
}
