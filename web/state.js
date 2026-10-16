/** Browser-native board state. Coordinates and saved documents use metres. */

export const PITCH_LENGTH_M = 105;
export const PITCH_WIDTH_M = 68;
export const STORAGE_KEY = "tactical-board.tactic.v1";
export const STATE_VERSION = 1;
export const MAX_JSON_BYTES = 1024 * 1024;
export const MAX_ARROWS = 200;
export const FORMATIONS = Object.freeze({
  "4-4-2": [4, 4, 2],
  "4-3-3": [4, 3, 3],
  "4-1-2-3": [4, 1, 2, 3],
  "3-5-2": [3, 5, 2],
  "4-2-3-1": [4, 2, 3, 1],
  "5-3-2": [5, 3, 2],
  "3-4-3": [3, 4, 3],
});

const POSITIONS = new Set(["GK", "DF", "MF", "FW"]);
const KIT_PATTERNS = new Set(["solid", "stripes", "vertical_stripes", "hoops", "halves"]);
const IMPORTED_ID = /^zerozero-([1-9][0-9]*)-(home|away)$/;
const MAX_SAFE_ID = Number.MAX_SAFE_INTEGER;

function fail(message) { throw new Error(message); }
function clone(value) { return JSON.parse(JSON.stringify(value)); }
function finite(value, min, max, label) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) {
    fail(`Invalid ${label}`);
  }
  return value;
}
function integer(value, min, max, label) {
  if (!Number.isSafeInteger(value) || value < min || value > max) fail(`Invalid ${label}`);
  return value;
}
function name(value, label) {
  if (typeof value !== "string" || !value.trim() || value.length > 120 || /[\x00-\x1f]/.test(value)) {
    fail(`Invalid ${label}`);
  }
  return value.trim();
}
function sideIndexOf(side) {
  if (side === 0 || side === "A") return 0;
  if (side === 1 || side === "B") return 1;
  fail("Invalid team side");
}
function slotIndexOf(slot) { return integer(slot, 0, 10, "player slot"); }
function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }
function linearlySpaced(start, stop, count) {
  if (count === 1) return [(start + stop) / 2];
  return Array.from({ length: count }, (_, index) => start + (stop - start) * index / (count - 1));
}
function rowYs(count) {
  if (count === 1) return [PITCH_WIDTH_M / 2];
  if (count === 2) return [PITCH_WIDTH_M * 0.38, PITCH_WIDTH_M * 0.62];
  return linearlySpaced(7, PITCH_WIDTH_M - 7, count);
}

/** Eleven [x,y] formation homes, GK first; side 1/B is mirrored. */
export function formationSlots(formation, side = 0) {
  const rows = FORMATIONS[formation];
  if (!rows) fail("Unknown formation");
  const mirror = sideIndexOf(side) === 1;
  const coordinates = [[3, PITCH_WIDTH_M / 2]];
  const depths = linearlySpaced(14, 48, rows.length);
  rows.forEach((count, row) => {
    for (const y of rowYs(count)) coordinates.push([depths[row], y]);
  });
  return mirror ? coordinates.map(([x, y]) => [PITCH_LENGTH_M - x, y]) : coordinates;
}

function playerIdentity(player) {
  return `${player.name}\u0000${player.number}\u0000${player.position}`;
}
function samePlayer(a, b) {
  return a.name === b.name && a.number === b.number && a.position === b.position;
}
function makeSlot(player, [x, y]) {
  return {
    number: player.number, name: player.name, position: player.position,
    x_m: x, y_m: y,
    ...(player.id == null ? {} : { player_id: player.id }),
  };
}

function positionCounts(formation) {
  const rows = FORMATIONS[formation];
  return { DF: rows[0], MF: rows.slice(1, -1).reduce((a, b) => a + b, 0), FW: rows.at(-1) };
}

function initialPlayers(team, formation) {
  const squad = team.squad;
  if (!Array.isArray(squad)) fail("Invalid team squad");
  if (Array.isArray(team.starting_ids)) {
    const byId = new Map(squad.map(player => [player.id, player]));
    const starters = team.starting_ids.map(id => byId.get(id));
    if (starters.some(player => !player)) fail("Invalid starting eleven");
    const gk = starters.find(player => player.position === "GK");
    if (!gk) fail("The starting eleven needs a goalkeeper");
    return [gk, ...starters.filter(player => player !== gk)];
  }
  const gk = squad.find(player => player.position === "GK");
  if (!gk) fail("The team needs a goalkeeper");
  const selected = [gk];
  const used = new Set([gk.number]);
  for (const [position, count] of Object.entries(positionCounts(formation))) {
    let filled = 0;
    for (const player of squad) {
      if (filled === count) break;
      if (player.position !== position || used.has(player.number)) continue;
      selected.push(player);
      used.add(player.number);
      filled += 1;
    }
  }
  for (const player of squad) {
    if (selected.length === 11) break;
    if (player.position !== "GK" && !used.has(player.number)) {
      selected.push(player);
      used.add(player.number);
    }
  }
  if (selected.length !== 11) fail("The team needs ten distinct outfield shirt numbers");
  return selected;
}

function makeSide(team, sideIndex, formationOverride = null) {
  if (!team || typeof team.id !== "string" || !Array.isArray(team.kits) || !team.kits.length) {
    fail("Invalid team");
  }
  const imported = team.id.startsWith("zerozero-");
  const formation = imported
    ? (FORMATIONS[team.formation] ? team.formation : "4-3-3")
    : (FORMATIONS[formationOverride] ? formationOverride : FORMATIONS[team.formation] ? team.formation : "4-4-2");
  const starters = initialPlayers(team, formation);
  const homes = formationSlots(formation, sideIndex);
  const players = starters.map((person, index) => makeSlot(person, homes[index]));
  if (imported && Array.isArray(team.substitutions)) {
    const byId = new Map(team.squad.map(person => [person.id, person]));
    const byOutgoing = new Map(team.substitutions.map(change => [change.out_id, change]));
    players.forEach((slot, index) => {
      const change = byOutgoing.get(slot.player_id);
      if (!change) return;
      const after = byId.get(change.in_id);
      if (!after || (after.position === "GK") !== (index === 0)) return;
      slot.switch_pair = { before: clone(byId.get(change.out_id)), after: clone(after), minute: change.minute };
      slot.switch_active = false;
    });
  }
  return {
    team_id: team.id, kit_index: 0, formation, players,
    ...(imported ? { team_data: clone(team) } : {}),
  };
}

/** Build the same version-1 tactic document used by the Python app. */
export function createInitialState(teams) {
  if (!Array.isArray(teams) || teams.length < 2) fail("At least two teams are required");
  return {
    version: STATE_VERSION,
    sides: [makeSide(teams[0], 0), makeSide(teams[1], 1)],
    arrows: [], ball: null,
  };
}

function validateColor(value) {
  if (!Array.isArray(value) || value.length !== 3 || value.some(channel => !Number.isInteger(channel) || channel < 0 || channel > 255)) {
    fail("Invalid kit color");
  }
  return [...value];
}
function validateKit(kit) {
  if (!kit || typeof kit !== "object") fail("Invalid kit");
  const pattern = kit.pattern;
  if (!KIT_PATTERNS.has(pattern)) fail("Invalid kit pattern");
  if (!Array.isArray(kit.colors) || kit.colors.length < 1 || kit.colors.length > 2) fail("Invalid kit colors");
  return { name: name(kit.name, "kit name"), pattern, colors: kit.colors.map(validateColor) };
}
function validatePerson(person) {
  if (!person || typeof person !== "object") fail("Invalid player");
  if (!POSITIONS.has(person.position)) fail("Invalid player position");
  return {
    id: integer(person.id, 1, MAX_SAFE_ID, "player ID"),
    number: integer(person.number, 1, 999, "shirt number"),
    name: name(person.name, "player name"),
    position: person.position,
  };
}

/** Validate embedded match teams before accepting a tactic file. */
export function validateImportedTeam(team) {
  if (!team || typeof team !== "object") fail("Invalid imported team");
  const match = typeof team.id === "string" ? IMPORTED_ID.exec(team.id) : null;
  if (!match) fail("Invalid imported team ID");
  const matchId = integer(Number(match[1]), 1, MAX_SAFE_ID, "match ID");
  const source = { provider: "zerozero", match_id: matchId, side: match[2] };
  if (team.source != null &&
      (team.source.provider !== source.provider || team.source.match_id !== matchId || team.source.side !== source.side)) {
    fail("Invalid imported team source");
  }
  if (!Array.isArray(team.kits) || team.kits.length < 1 || team.kits.length > 5) fail("Invalid team kits");
  if (!Array.isArray(team.squad) || team.squad.length < 11 || team.squad.length > 40) fail("Invalid team squad");
  const squad = team.squad.map(validatePerson);
  if (new Set(squad.map(player => player.id)).size !== squad.length ||
      new Set(squad.map(player => player.number)).size !== squad.length) {
    fail("Duplicate player or shirt number");
  }
  const byId = new Map(squad.map(player => [player.id, player]));
  if (!Array.isArray(team.starting_ids) || team.starting_ids.length !== 11 ||
      new Set(team.starting_ids).size !== 11 || team.starting_ids.some(id => !byId.has(id))) {
    fail("Invalid starting eleven");
  }
  const goalkeepers = team.starting_ids.filter(id => byId.get(id).position === "GK");
  if (goalkeepers.length !== 1) fail("The starting eleven needs exactly one goalkeeper");
  const startingIds = [goalkeepers[0], ...team.starting_ids.filter(id => id !== goalkeepers[0])];
  if (team.formation != null && !FORMATIONS[team.formation]) fail("Invalid imported formation");
  const changes = team.substitutions ?? [];
  if (!Array.isArray(changes) || changes.length > 20) fail("Invalid substitutions");
  const substitutions = changes.map(change => ({
    out_id: integer(change?.out_id, 1, MAX_SAFE_ID, "substituted player ID"),
    in_id: integer(change?.in_id, 1, MAX_SAFE_ID, "substitute player ID"),
    minute: integer(change?.minute, 0, 180, "substitution minute"),
  })).sort((a, b) => a.minute - b.minute);
  const active = new Set(startingIds);
  const entered = new Set(startingIds);
  for (const change of substitutions) {
    if (!active.has(change.out_id) || entered.has(change.in_id) || !byId.has(change.in_id) ||
        byId.get(change.out_id).position === "GK" !== (byId.get(change.in_id).position === "GK")) {
      fail("Inconsistent substitution sequence");
    }
    active.delete(change.out_id);
    active.add(change.in_id);
    entered.add(change.in_id);
  }
  return {
    id: team.id, name: name(team.name, "team name"), kits: team.kits.map(validateKit),
    gk_kit: validateKit(team.gk_kit), squad, starting_ids: startingIds,
    substitutions, formation: team.formation ?? null, source,
  };
}

/** Team object for a state side, from static data or its embedded match team. */
export function resolveTeam(state, teams, side) {
  const index = sideIndexOf(side);
  const saved = state?.sides?.[index];
  if (!saved) fail("Missing team side");
  if (saved.team_id.startsWith("zerozero-")) return saved.team_data;
  const team = teams.find(candidate => candidate.id === saved.team_id);
  if (!team) fail("Unknown team in tactic");
  return team;
}

function validatePoint(point, label) {
  if (!Array.isArray(point) || point.length !== 2) fail(`Invalid ${label}`);
  return [finite(point[0], 0, PITCH_LENGTH_M, `${label} X`), finite(point[1], 0, PITCH_WIDTH_M, `${label} Y`)];
}
function validateSwitchPair(pair, active, player, team, slotIndex) {
  if (!pair || typeof pair !== "object" || typeof active !== "boolean") fail("Invalid substitution");
  const before = validatePerson(pair.before);
  const after = validatePerson(pair.after);
  const byId = new Map(team.squad.map(person => [person.id, person]));
  for (const person of [before, after]) {
    if (!samePlayer(byId.get(person.id) ?? {}, person)) fail("Invalid substitution player");
    if ((person.position === "GK") !== (slotIndex === 0)) fail("Invalid substitution position");
  }
  const minute = integer(pair.minute, 0, 180, "substitution minute");
  if (!team.substitutions.some(change => change.out_id === before.id && change.in_id === after.id && change.minute === minute)) {
    fail("Substitution is not recorded for this match");
  }
  const selected = active ? after : before;
  if (!samePlayer(selected, player) || selected.id !== player.player_id) fail("Substitution does not match player in tactic");
  return { before, after, minute };
}

/** Validate and normalize a v1 tactic while retaining its JSON contract. */
export function validateTactic(input, teams) {
  if (!input || typeof input !== "object" || input.version !== STATE_VERSION) fail("Unsupported tactic version");
  if (!Array.isArray(input.sides) || input.sides.length !== 2) fail("A tactic must contain two teams");
  const sides = input.sides.map((saved, sideIndex) => {
    if (!saved || typeof saved.team_id !== "string") fail("Unknown team in tactic");
    const imported = saved.team_id.startsWith("zerozero-");
    const team = imported ? validateImportedTeam(saved.team_data) : teams.find(candidate => candidate.id === saved.team_id);
    if (!team || team.id !== saved.team_id) fail("Unknown team in tactic");
    if (!FORMATIONS[saved.formation]) fail("Unknown formation in tactic");
    const kitIndex = integer(saved.kit_index, 0, team.kits.length - 1, "kit in tactic");
    if (!Array.isArray(saved.players) || saved.players.length !== 11) fail("A team must have eleven players");
    const validIdentities = new Set(team.squad.map(playerIdentity));
    const identities = new Set();
    const numbers = new Set();
    const players = saved.players.map((raw, slotIndex) => {
      if (!raw || typeof raw !== "object") fail("Invalid player in tactic");
      const person = { name: raw.name, number: raw.number, position: raw.position };
      if (typeof person.name !== "string" || !Number.isSafeInteger(person.number) || !POSITIONS.has(person.position)) {
        fail("Invalid player identity in tactic");
      }
      const identity = playerIdentity(person);
      if (!validIdentities.has(identity)) fail("Player is not in this team");
      if (identities.has(identity) || numbers.has(person.number)) fail("A duplicate player or shirt number was found");
      if ((person.position === "GK") !== (slotIndex === 0)) fail("Goalkeeper is assigned to an invalid slot");
      identities.add(identity);
      numbers.add(person.number);
      const player = {
        number: person.number, name: person.name, position: person.position,
        x_m: finite(raw.x_m, 0, PITCH_LENGTH_M, "player X"),
        y_m: finite(raw.y_m, 0, PITCH_WIDTH_M, "player Y"),
      };
      if (raw.player_id != null) {
        const candidate = team.squad.find(item => item.id === raw.player_id);
        if (!candidate || !samePlayer(candidate, person)) fail("Invalid imported player ID in tactic");
        player.player_id = raw.player_id;
      }
      if (raw.switch_pair != null) {
        if (!imported) fail("Invalid substitution in tactic");
        player.switch_pair = validateSwitchPair(raw.switch_pair, raw.switch_active, raw, team, slotIndex);
        player.switch_active = raw.switch_active;
      }
      return player;
    });
    return {
      team_id: team.id, kit_index: kitIndex, formation: saved.formation, players,
      ...(imported ? { team_data: team } : {}),
    };
  });
  if (!Array.isArray(input.arrows) || input.arrows.length > MAX_ARROWS) fail("Invalid arrows in tactic");
  const arrows = input.arrows.map(arrow => {
    if (!Array.isArray(arrow) || arrow.length !== 2) fail("Invalid arrow in tactic");
    return [validatePoint(arrow[0], "arrow start"), validatePoint(arrow[1], "arrow end")];
  });
  const ball = input.ball == null ? null : validatePoint(input.ball, "ball position");
  return { version: STATE_VERSION, sides, arrows, ball };
}

/** JSON export; rejects non-finite values and files over the historic 1 MB limit. */
export function serializeTactic(state, teams) {
  const text = JSON.stringify(validateTactic(state, teams), null, 2) + "\n";
  if (new TextEncoder().encode(text).length > MAX_JSON_BYTES) fail("Tactic exceeds the 1 MB limit");
  return text;
}

/** JSON import, including documents saved by the Python/Pygbag version. */
export function deserializeTactic(text, teams) {
  if (typeof text !== "string" || new TextEncoder().encode(text).length > MAX_JSON_BYTES) fail("Tactic exceeds the 1 MB limit");
  let parsed;
  try { parsed = JSON.parse(text); }
  catch { fail("Invalid tactic JSON"); }
  return validateTactic(parsed, teams);
}

/** Candidate squad members for an on-field slot. */
export function eligiblePlayers(state, teams, side, slot) {
  const sideIndex = sideIndexOf(side);
  const slotIndex = slotIndexOf(slot);
  const team = resolveTeam(state, teams, sideIndex);
  const occupied = new Set(state.sides[sideIndex].players.filter((_, index) => index !== slotIndex).map(player => player.number));
  return team.squad.filter(player => (player.position === "GK") === (slotIndex === 0) && !occupied.has(player.number));
}

/** Replace either team's selection and starting eleven. */
export function setTeam(state, side, team) {
  const index = sideIndexOf(side);
  const next = clone(state);
  const selected = team.id.startsWith("zerozero-") ? validateImportedTeam(team) : team;
  next.sides[index] = makeSide(selected, index, next.sides[index].formation);
  return next;
}

export function setKit(state, side, kitIndex, teams) {
  const index = sideIndexOf(side);
  const team = resolveTeam(state, teams, index);
  integer(kitIndex, 0, team.kits.length - 1, "kit index");
  const next = clone(state);
  next.sides[index].kit_index = kitIndex;
  return next;
}

/** Keep players and their displacement from previous formation homes. */
export function setFormation(state, side, formation) {
  if (!FORMATIONS[formation]) fail("Unknown formation");
  const index = sideIndexOf(side);
  const next = clone(state);
  const selected = next.sides[index];
  if (selected.formation === formation) return next;
  const oldHomes = formationSlots(selected.formation, index);
  const newHomes = formationSlots(formation, index);
  const remaining = selected.players.slice(1).map((player, oldIndex) => ({ player, home: oldHomes[oldIndex + 1] }));
  const rows = FORMATIONS[formation];
  const roles = rows.flatMap((count, row) => Array(count).fill(row === 0 ? "DF" : row === rows.length - 1 ? "FW" : "MF"));
  const reassigned = roles.map((role, newIndex) => {
    let found = remaining.findIndex(item => item.player.position === role);
    if (found < 0) found = 0;
    const [{ player, home }] = remaining.splice(found, 1);
    const target = newHomes[newIndex + 1];
    player.x_m = clamp(target[0] + player.x_m - home[0], 0, PITCH_LENGTH_M);
    player.y_m = clamp(target[1] + player.y_m - home[1], 0, PITCH_WIDTH_M);
    return player;
  });
  selected.formation = formation;
  selected.players = [selected.players[0], ...reassigned];
  return next;
}

export function setPlayer(state, teams, side, slot, person) {
  const index = sideIndexOf(side);
  const slotIndex = slotIndexOf(slot);
  const candidate = eligiblePlayers(state, teams, index, slotIndex).find(item =>
    samePlayer(item, person) && (person.id == null || person.id === item.id));
  if (!candidate) fail("Player is unavailable for this slot");
  const next = clone(state);
  const target = next.sides[index].players[slotIndex];
  target.name = candidate.name;
  target.number = candidate.number;
  target.position = candidate.position;
  if (candidate.id == null) delete target.player_id;
  else target.player_id = candidate.id;
  delete target.switch_pair;
  delete target.switch_active;
  return next;
}

export function movePlayer(state, side, slot, x, y) {
  const next = clone(state);
  const target = next.sides[sideIndexOf(side)].players[slotIndexOf(slot)];
  target.x_m = clamp(finite(x, -Infinity, Infinity, "player X"), 0, PITCH_LENGTH_M);
  target.y_m = clamp(finite(y, -Infinity, Infinity, "player Y"), 0, PITCH_WIDTH_M);
  return next;
}

export function toggleSubstitution(state, side, slot) {
  const index = sideIndexOf(side);
  const slotIndex = slotIndexOf(slot);
  const next = clone(state);
  const selected = next.sides[index];
  const target = selected.players[slotIndex];
  if (!target.switch_pair) fail("This player has no match substitution");
  const replacement = target.switch_pair[target.switch_active ? "before" : "after"];
  if (selected.players.some((player, i) => i !== slotIndex && player.number === replacement.number)) {
    fail("The substitute's shirt number is already on the pitch");
  }
  target.name = replacement.name;
  target.number = replacement.number;
  target.position = replacement.position;
  target.player_id = replacement.id;
  target.switch_active = !target.switch_active;
  return next;
}

export function resetPositions(state) {
  const next = clone(state);
  next.sides.forEach((side, index) => {
    const homes = formationSlots(side.formation, index);
    side.players.forEach((player, slot) => { [player.x_m, player.y_m] = homes[slot]; });
  });
  return next;
}

export function addArrow(state, start, end) {
  const next = clone(state);
  if (next.arrows.length >= MAX_ARROWS) fail("The tactic has too many arrows");
  const a = validatePoint(start, "arrow start");
  const b = validatePoint(end, "arrow end");
  if (a[0] !== b[0] || a[1] !== b[1]) next.arrows.push([a, b]);
  return next;
}

export function setBall(state, point) {
  const next = clone(state);
  next.ball = point == null ? null : validatePoint(point, "ball position");
  return next;
}

export function clearAnnotations(state) {
  const next = clone(state);
  next.arrows = [];
  next.ball = null;
  return next;
}

/** History shape: {past: State[], present: State}; cap mirrors Python's 50 edits. */
export function createHistory(initial) { return { past: [], present: clone(initial) }; }
export function commit(history, next) {
  return { past: [...history.past, clone(history.present)].slice(-50), present: clone(next) };
}
export function undo(history) {
  if (!history.past.length) return history;
  return { past: history.past.slice(0, -1), present: clone(history.past.at(-1)) };
}
