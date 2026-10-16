"""Native browser controls for the pygbag tactical board.

The canvas remains the visual editor. In the web build, this module adds a
collapsible HTML form with the same state and actions so assistive technology
can discover and operate individual controls. The Python board owns the state;
JavaScript only queues user commands and renders the supplied snapshot.
"""

import json
import sys


_INSTALL_JS = r"""
(() => {
  if (window.__tacticalBoardAccessibility) return true;
  window.boardCommands = window.boardCommands || [];
  const send = command => window.boardCommands.push(command);
  const doc = window.document;

  const style = doc.createElement('style');
  style.id = 'tactical-board-accessibility-style';
  style.textContent = `
    #tactical-board-accessibility {
      position: fixed; z-index: 1000; right: 12px; bottom: 12px;
      box-sizing: border-box; width: min(360px, calc(100vw - 24px));
      max-height: calc(100vh - 24px); overflow: auto;
      padding: 8px 10px; border: 2px solid #1b4d2e; border-radius: 8px;
      background: #fff; color: #111; box-shadow: 0 3px 16px #0008;
      font: 16px/1.35 system-ui, sans-serif;
    }
    #tactical-board-accessibility:not([open]) {
      width: auto; max-width: calc(100vw - 24px);
    }
    #tactical-board-accessibility summary { cursor: pointer; font-weight: 700; }
    #tactical-board-accessibility fieldset { margin: 10px 0; border: 1px solid #666; }
    #tactical-board-accessibility label { display: block; margin: 8px 0 3px; }
    #tactical-board-accessibility select,
    #tactical-board-accessibility input,
    #tactical-board-accessibility button {
      box-sizing: border-box; min-height: 40px; width: 100%;
      font: inherit; color: #111;
    }
    #tactical-board-accessibility .tb-coordinates,
    #tactical-board-accessibility .tb-actions {
      display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px;
    }
    #tactical-board-accessibility .tb-coordinates label { margin-top: 0; }
    #tactical-board-accessibility button { cursor: pointer; margin-top: 5px; }
    #tactical-board-accessibility :focus-visible { outline: 3px solid #1456ba; outline-offset: 2px; }
  `;
  doc.head.appendChild(style);

  const details = doc.createElement('details');
  details.id = 'tactical-board-accessibility';
  const summary = doc.createElement('summary');
  summary.textContent = 'Accessible tactical controls';
  details.appendChild(summary);

  function element(tag, parent, text) {
    const node = doc.createElement(tag);
    if (text !== undefined) node.textContent = text;
    parent.appendChild(node);
    return node;
  }
  function labelledSelect(parent, id, label) {
    const labelNode = element('label', parent, label);
    labelNode.htmlFor = id;
    const select = element('select', parent);
    select.id = id;
    return select;
  }
  function labelledNumber(parent, id, label, max) {
    const labelNode = element('label', parent, label);
    labelNode.htmlFor = id;
    const input = element('input', parent);
    input.id = id;
    input.type = 'number';
    input.min = '0';
    input.max = String(max);
    input.step = 'any';
    input.required = true;
    return input;
  }
  function labelledUrl(parent, id, label) {
    const labelNode = element('label', parent, label);
    labelNode.htmlFor = id;
    const input = element('input', parent);
    input.id = id;
    input.type = 'url';
    input.inputMode = 'url';
    input.autocapitalize = 'off';
    input.spellcheck = false;
    input.required = true;
    input.maxLength = 2048;
    input.placeholder = 'https://www.zerozero.pt/jogo/...';
    return input;
  }
  function button(parent, label, action) {
    const node = element('button', parent, label);
    node.type = 'button';
    node.dataset.action = action;
    return node;
  }
  function setOptions(select, entries, value) {
    // Keep the current DOM nodes and browser focus when the choices are stable.
    const signature = JSON.stringify(entries);
    if (select.dataset.options !== signature) {
      select.textContent = '';
      for (const [optionValue, label] of entries) {
        const option = doc.createElement('option');
        option.value = String(optionValue);
        option.textContent = label;
        select.appendChild(option);
      }
      select.dataset.options = signature;
    }
    select.value = String(value);
  }

  const matchGroup = element('fieldset', details);
  element('legend', matchGroup, 'Import Zerozero match');
  const matchUrl = labelledUrl(matchGroup, 'tb-match-url', 'Zerozero match link');
  button(matchGroup, 'Import match', 'load_match');
  function loadMatch() {
    const url = matchUrl.value.trim();
    matchUrl.value = url;
    if (!matchUrl.reportValidity()) return;
    send({type: 'load_match', url});
  }
  matchUrl.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      loadMatch();
    }
  });

  const sideControls = {};
  for (const side of ['A', 'B']) {
    const group = element('fieldset', details);
    element('legend', group, `Side ${side}`);
    sideControls[side] = {
      team: labelledSelect(group, `tb-team-${side}`, 'Team'),
      kit: labelledSelect(group, `tb-kit-${side}`, 'Uniform'),
      formation: labelledSelect(group, `tb-formation-${side}`, 'Formation'),
    };
  }

  const playerGroup = element('fieldset', details);
  element('legend', playerGroup, 'Players');
  const slotSelect = labelledSelect(playerGroup, 'tb-slot', 'Player slot');
  const playerSelect = labelledSelect(playerGroup, 'tb-player', 'Eligible player');
  const switchButton = button(playerGroup, 'Switch player', 'switch_player');
  switchButton.hidden = true;
  switchButton.disabled = true;
  const coordinates = element('div', playerGroup);
  coordinates.className = 'tb-coordinates';
  const xGroup = element('div', coordinates);
  const yGroup = element('div', coordinates);
  const xInput = labelledNumber(xGroup, 'tb-x', 'X position (metres)', 105);
  const yInput = labelledNumber(yGroup, 'tb-y', 'Y position (metres)', 68);
  button(playerGroup, 'Move selected player', 'move_player');

  const toolGroup = element('fieldset', details);
  element('legend', toolGroup, 'Drawing');
  const modeSelect = labelledSelect(toolGroup, 'tb-mode', 'Tool mode');
  setOptions(modeSelect, [['move', 'Move'], ['arrow', 'Arrow'], ['ball', 'Ball']], 'move');

  const annotationGroup = element('fieldset', details);
  element('legend', annotationGroup, 'Arrows and ball');
  const arrowStartGroup = element('div', annotationGroup);
  arrowStartGroup.className = 'tb-coordinates';
  const arrowStartX = labelledNumber(element('div', arrowStartGroup),
    'tb-arrow-start-x', 'Arrow start X (metres)', 105);
  const arrowStartY = labelledNumber(element('div', arrowStartGroup),
    'tb-arrow-start-y', 'Arrow start Y (metres)', 68);
  const arrowEndGroup = element('div', annotationGroup);
  arrowEndGroup.className = 'tb-coordinates';
  const arrowEndX = labelledNumber(element('div', arrowEndGroup),
    'tb-arrow-end-x', 'Arrow end X (metres)', 105);
  const arrowEndY = labelledNumber(element('div', arrowEndGroup),
    'tb-arrow-end-y', 'Arrow end Y (metres)', 68);
  arrowStartX.value = '20'; arrowStartY.value = '34';
  arrowEndX.value = '40'; arrowEndY.value = '34';
  button(annotationGroup, 'Add arrow', 'add_arrow');
  const ballGroup = element('div', annotationGroup);
  ballGroup.className = 'tb-coordinates';
  const ballX = labelledNumber(element('div', ballGroup),
    'tb-ball-x', 'Ball X (metres)', 105);
  const ballY = labelledNumber(element('div', ballGroup),
    'tb-ball-y', 'Ball Y (metres)', 68);
  ballX.value = '52.5'; ballY.value = '34';
  button(annotationGroup, 'Place ball', 'place_ball');
  let ballDraftDirty = false;
  let latestBall = null;
  function syncBallInputs() {
    if (!latestBall || ballDraftDirty ||
        doc.activeElement === ballX || doc.activeElement === ballY) return;
    ballX.value = String(latestBall[0]);
    ballY.value = String(latestBall[1]);
  }
  for (const input of [ballX, ballY]) {
    input.addEventListener('input', () => { ballDraftDirty = true; });
    input.addEventListener('blur', syncBallInputs);
    input.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        ballDraftDirty = false;
        input.blur();
        syncBallInputs();
      }
    });
  }

  const actionGroup = element('fieldset', details);
  element('legend', actionGroup, 'Tactic actions');
  const actions = element('div', actionGroup);
  actions.className = 'tb-actions';
  for (const [label, action] of [
    ['Undo', 'undo'], ['Reset positions', 'reset'],
    ['Save', 'save'], ['Load', 'load'], ['Import JSON', 'import_json'],
    ['Export JSON', 'export_json'], ['Export PNG', 'export_png'],
    ['Clear arrows and ball', 'clear_annotations'],
  ]) button(actions, label, action);
  const annotationSummary = element('p', details);
  annotationSummary.id = 'tb-annotation-summary';
  const arrowList = element('ol', details);
  arrowList.setAttribute('aria-label', 'Drawn arrows');

  doc.body.appendChild(details);
  let state = null;

  function selectedSlot() {
    const parts = slotSelect.value.split(':');
    const side = parts[0];
    const slot = Number(parts[1]);
    if ((side !== 'A' && side !== 'B') || !Number.isInteger(slot) || slot < 0 || slot > 10) return null;
    return {side, slot};
  }
  function sideState(side) { return state.sides[side === 'A' ? 0 : 1]; }
  function availableTeams() {
    const teams = new Map();
    for (const team of state.teams || []) teams.set(String(team.id), team);
    for (const saved of state.sides) {
      const embedded = saved.team;
      if (embedded && embedded.id != null) teams.set(String(embedded.id), embedded);
      else if (!teams.has(String(saved.team_id))) {
        teams.set(String(saved.team_id), {
          id: saved.team_id,
          name: saved.team_name || saved.team_id,
          kits: saved.kits || [{name: 'Match uniform'}],
          squad: saved.squad || saved.players || [],
        });
      }
    }
    return [...teams.values()];
  }
  function selectedTeam(side) {
    return availableTeams().find(team => String(team.id) === String(sideState(side).team_id));
  }
  function playerKey(player) {
    return JSON.stringify([player.name, player.number, player.position]);
  }
  function updateSelectedPlayer() {
    switchButton.hidden = true;
    switchButton.disabled = true;
    if (!state) return;
    const selection = selectedSlot();
    if (!selection) return;
    const side = sideState(selection.side);
    const current = side.players[selection.slot];
    const team = selectedTeam(selection.side);
    if (!current || !team) return;
    const occupied = new Set(side.players
      .filter((_, index) => index !== selection.slot)
      .map(player => Number(player.number)));
    const eligible = (team.squad || []).filter(player =>
      (player.position === 'GK') === (selection.slot === 0) &&
      !occupied.has(Number(player.number)));
    setOptions(playerSelect,
      eligible.map(player => [playerKey(player),
        `#${player.number} ${player.name} (${player.position})`]),
      playerKey(current));
    const pair = current.switch_pair;
    const target = pair && pair[current.switch_active ? 'before' : 'after'];
    if (target && target.name && target.number != null) {
      switchButton.textContent = `Switch to #${target.number} ${target.name}`;
      switchButton.hidden = false;
      switchButton.disabled = false;
    }
    xInput.value = String(current.x_m);
    yInput.value = String(current.y_m);
  }

  function update(nextState) {
    state = nextState;
    const teamEntries = availableTeams().map(team => [team.id, team.name]);
    for (const side of ['A', 'B']) {
      const saved = sideState(side);
      const team = selectedTeam(side);
      const controls = sideControls[side];
      setOptions(controls.team, teamEntries, saved.team_id);
      setOptions(controls.kit,
        (team.kits || []).map((kit, index) => [index, kit.name]), saved.kit_index);
      setOptions(controls.formation,
        state.formations.map(name => [name, name]), saved.formation);
    }
    const slots = [];
    for (const side of ['A', 'B']) {
      sideState(side).players.forEach((player, index) =>
        slots.push([`${side}:${index}`,
          `${side}, ${index === 0 ? 'goalkeeper' : `slot ${index}`}: #${player.number} ${player.name}`]));
    }
    const oldSlot = slotSelect.value;
    setOptions(slotSelect, slots, slots.some(([key]) => key === oldSlot) ? oldSlot : 'A:0');
    updateSelectedPlayer();
    modeSelect.value = state.mode;
    const arrowCount = Array.isArray(state.arrows) ? state.arrows.length : 0;
    const ball = state.ball;
    latestBall = ball;
    syncBallInputs();
    annotationSummary.textContent = `${arrowCount} arrow${arrowCount === 1 ? '' : 's'}. ` +
      (ball ? `Ball at X ${ball[0]} metres, Y ${ball[1]} metres.` : 'No ball placed.');
    arrowList.textContent = '';
    for (const [index, arrow] of (state.arrows || []).entries()) {
      const [start, end] = arrow;
      element('li', arrowList,
        `Arrow ${index + 1}: from X ${start[0]}, Y ${start[1]} metres ` +
        `to X ${end[0]}, Y ${end[1]} metres.`);
    }
  }

  details.addEventListener('change', event => {
    if (!state) return;
    const target = event.target;
    if (target === slotSelect) { updateSelectedPlayer(); return; }
    if (target === playerSelect) {
      const selection = selectedSlot();
      if (selection) {
        const [name, number, position] = JSON.parse(playerSelect.value);
        send({type: 'select_player', ...selection, player: {name, number, position}});
      }
      return;
    }
    if (target === modeSelect) { send({type: 'set_mode', mode: modeSelect.value}); return; }
    for (const side of ['A', 'B']) {
      const controls = sideControls[side];
      if (target === controls.team) {
        send({type: 'set_team', side, value: controls.team.value}); return;
      }
      if (target === controls.kit) {
        send({type: 'set_kit', side, value: Number(controls.kit.value)}); return;
      }
      if (target === controls.formation) {
        send({type: 'set_formation', side, value: controls.formation.value}); return;
      }
    }
  });
  details.addEventListener('click', event => {
    const action = event.target.dataset.action;
    if (!action) return;
    if (action === 'load_match') {
      loadMatch();
    } else if (action === 'switch_player') {
      const selection = selectedSlot();
      if (selection && !switchButton.disabled)
        send({type: 'switch_player', ...selection});
    } else if (action === 'move_player') {
      const selection = selectedSlot();
      if (!selection || !xInput.reportValidity() || !yInput.reportValidity()) return;
      const x_m = Number(xInput.value);
      const y_m = Number(yInput.value);
      if (Number.isFinite(x_m) && Number.isFinite(y_m))
        send({type: 'move_player', ...selection, x_m, y_m});
    } else if (action === 'add_arrow') {
      const inputs = [arrowStartX, arrowStartY, arrowEndX, arrowEndY];
      if (!inputs.every(input => input.reportValidity())) return;
      const [sx, sy, ex, ey] = inputs.map(input => Number(input.value));
      if ([sx, sy, ex, ey].every(Number.isFinite))
        send({type: 'add_arrow', start: [sx, sy], end: [ex, ey]});
    } else if (action === 'place_ball') {
      if (!ballX.reportValidity() || !ballY.reportValidity()) return;
      const point = [Number(ballX.value), Number(ballY.value)];
      if (point.every(Number.isFinite)) {
        ballDraftDirty = false;
        send({type: 'place_ball', point});
      }
    } else {
      send({type: 'action', action});
    }
  });
  window.__tacticalBoardAccessibility = {update};
  return true;
})()
"""


class WebAccessibilityPanel:
    """Python half of the DOM command queue and state view."""

    def __init__(self, window):
        self._window = window
        self._last_json = None

    def update(self, state: dict) -> None:
        """Refresh native controls when the board snapshot changes."""
        payload = json.dumps(state, ensure_ascii=True, allow_nan=False)
        if payload == self._last_json:
            return
        self._window.eval(f"window.__tacticalBoardAccessibility.update({payload})")
        self._last_json = payload

    def drain_commands(self) -> list[dict]:
        """Take queued browser commands in order, exactly once."""
        raw = self._window.eval("JSON.stringify(window.boardCommands.splice(0))")
        commands = json.loads(str(raw))
        if not isinstance(commands, list) or not all(isinstance(command, dict) for command in commands):
            raise ValueError("The browser command queue contains invalid data")
        return commands


def create_panel() -> WebAccessibilityPanel | None:
    """Create browser controls, or return None in the desktop build."""
    if sys.platform != "emscripten":
        return None
    from platform import window

    window.eval(_INSTALL_JS)
    return WebAccessibilityPanel(window)
