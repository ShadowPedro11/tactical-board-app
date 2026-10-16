import test from "node:test";
import assert from "node:assert/strict";
import {
  FORMATIONS, STORAGE_KEY, PITCH_LENGTH_M, PITCH_WIDTH_M, formationSlots,
  createInitialState, resolveTeam, eligiblePlayers, validateImportedTeam,
  validateTactic, serializeTactic, deserializeTactic, setTeam, setKit,
  setFormation, setPlayer, movePlayer, toggleSubstitution, resetPositions,
  addArrow, setBall, clearAnnotations, createHistory, commit, undo,
} from "./state.js";

function staticTeam(id) {
  const players = [
    { number: 1, name: `${id} Keeper`, position: "GK" },
    ...Array.from({ length: 6 }, (_, i) => ({ number: i + 2, name: `${id} Defender ${i}`, position: "DF" })),
    ...Array.from({ length: 6 }, (_, i) => ({ number: i + 8, name: `${id} Midfielder ${i}`, position: "MF" })),
    ...Array.from({ length: 5 }, (_, i) => ({ number: i + 14, name: `${id} Forward ${i}`, position: "FW" })),
  ];
  return {
    id, name: id, kits: [
      { name: "Home", pattern: "solid", colors: [[10, 20, 30]] },
      { name: "Away", pattern: "stripes", colors: [[200, 210, 220], [20, 30, 40]] },
    ],
    gk_kit: { name: "GK", pattern: "solid", colors: [[240, 196, 25]] },
    squad: players,
  };
}

function importedTeam() {
  const squad = Array.from({ length: 13 }, (_, i) => ({
    id: 101 + i, number: i + 1, name: `Match Player ${i + 1}`,
    position: i === 0 || i === 12 ? "GK" : i <= 4 ? "DF" : i <= 8 || i === 11 ? "MF" : "FW",
  }));
  return {
    id: "zerozero-12345-home", name: "Match FC",
    kits: [{ name: "Match", pattern: "vertical_stripes", colors: [[18, 52, 86], [255, 255, 255]] }],
    gk_kit: { name: "GK", pattern: "solid", colors: [[240, 196, 25]] },
    squad, starting_ids: squad.slice(0, 11).map(player => player.id),
    substitutions: [{ out_id: 106, in_id: 112, minute: 63 }],
    formation: "4-4-2",
    source: { provider: "zerozero", match_id: 12345, side: "home" },
  };
}

const teams = [staticTeam("home"), staticTeam("away")];

test("formation geometry has eleven unique homes and mirrors accurately", () => {
  assert.equal(PITCH_LENGTH_M, 105);
  assert.equal(PITCH_WIDTH_M, 68);
  for (const formation of Object.keys(FORMATIONS)) {
    const left = formationSlots(formation, 0);
    const right = formationSlots(formation, 1);
    assert.equal(left.length, 11);
    assert.equal(right.length, 11);
    assert.equal(new Set(left.map(point => point.join(","))).size, 11);
    left.forEach(([x, y], index) => assert.deepEqual(right[index], [105 - x, y]));
  }
  assert.deepEqual(formationSlots("4-4-2", 0)[0], [3, 34]);
  assert.deepEqual(formationSlots("4-4-2", 1)[0], [102, 34]);
});

test("initial state matches saved v1 shape and selects eleven distinct players", () => {
  const state = createInitialState(teams);
  assert.equal(STORAGE_KEY, "tactical-board.tactic.v1");
  assert.equal(state.version, 1);
  assert.deepEqual(state.ball, null);
  assert.deepEqual(state.arrows, []);
  for (const side of state.sides) {
    assert.equal(side.players.length, 11);
    assert.equal(side.players[0].position, "GK");
    assert.equal(new Set(side.players.map(player => player.number)).size, 11);
    assert.equal(side.formation, "4-4-2");
  }
  assert.equal(resolveTeam(state, teams, 0), teams[0]);
  assert.deepEqual(validateTactic(state, teams), state);
});

test("legacy version-1 JSON remains importable and exports under same keys", () => {
  const previous = createInitialState(teams);
  const text = JSON.stringify(previous);
  const imported = deserializeTactic(text, teams);
  assert.deepEqual(imported, previous);
  assert.deepEqual(JSON.parse(serializeTactic(imported, teams)), previous);
  assert.throws(() => deserializeTactic('{"version":2}', teams), /version/);
  assert.throws(() => deserializeTactic('{not json}', teams), /JSON/);
});

test("team, kit, picker, move, arrows, ball and reset are immutable", () => {
  const start = createInitialState(teams);
  const switchedTeam = setTeam(start, 0, teams[1]);
  assert.equal(start.sides[0].team_id, "home");
  assert.equal(switchedTeam.sides[0].team_id, "away");
  const kit = setKit(switchedTeam, 0, 1, teams);
  assert.equal(kit.sides[0].kit_index, 1);
  const slot = 1;
  const current = kit.sides[0].players[slot];
  const replacement = eligiblePlayers(kit, teams, 0, slot).find(person => person.position === current.position && person.number !== current.number);
  const selected = setPlayer(kit, teams, 0, slot, replacement);
  assert.equal(selected.sides[0].players[slot].number, replacement.number);
  const moved = movePlayer(selected, 0, slot, 999, -20);
  assert.deepEqual([moved.sides[0].players[slot].x_m, moved.sides[0].players[slot].y_m], [105, 0]);
  const annotated = setBall(addArrow(moved, [10, 11], [20, 21]), [52.5, 34]);
  assert.deepEqual(annotated.arrows, [[[10, 11], [20, 21]]]);
  assert.deepEqual(annotated.ball, [52.5, 34]);
  assert.deepEqual(clearAnnotations(annotated).arrows, []);
  assert.deepEqual(clearAnnotations(annotated).ball, null);
  assert.deepEqual(start.arrows, []);
  const reset = resetPositions(moved);
  assert.deepEqual(
    [reset.sides[0].players[slot].x_m, reset.sides[0].players[slot].y_m],
    formationSlots(reset.sides[0].formation, 0)[slot],
  );
});

test("formation changes keep identities and offsets from their old homes", () => {
  const start = createInitialState(teams);
  const oldSlot = start.sides[0].players[2];
  const moved = movePlayer(start, 0, 2, oldSlot.x_m + 1.5, oldSlot.y_m - 0.5);
  const changed = setFormation(moved, 0, "4-1-2-3");
  assert.equal(changed.sides[0].formation, "4-1-2-3");
  assert.deepEqual(
    changed.sides[0].players.map(player => [player.name, player.number]).sort(),
    moved.sides[0].players.map(player => [player.name, player.number]).sort(),
  );
  const same = changed.sides[0].players.find(player => player.name === oldSlot.name);
  const newIndex = changed.sides[0].players.indexOf(same);
  const newHome = formationSlots("4-1-2-3", 0)[newIndex];
  assert.ok(Math.abs(same.x_m - newHome[0] - 1.5) < 1e-9);
  assert.ok(Math.abs(same.y_m - newHome[1] + 0.5) < 1e-9);
  assert.deepEqual(validateTactic(changed, teams), changed);
});

test("imported match teams and substitution switches survive v1 JSON", () => {
  const match = validateImportedTeam(importedTeam());
  const state = setTeam(createInitialState(teams), 0, match);
  assert.equal(state.sides[0].team_id, match.id);
  assert.deepEqual(state.sides[0].players.map(player => player.player_id), match.starting_ids);
  assert.equal(state.sides[0].players[5].switch_pair.after.id, 112);
  const switched = toggleSubstitution(state, 0, 5);
  assert.equal(switched.sides[0].players[5].player_id, 112);
  assert.equal(switched.sides[0].players[5].number, 12);
  assert.equal(switched.sides[0].players[5].switch_active, true);
  const restored = deserializeTactic(serializeTactic(switched, teams), teams);
  assert.deepEqual(restored, switched);
  assert.deepEqual(toggleSubstitution(restored, 0, 5), state);
});

test("invalid embedded teams, duplicate shirts and mismatched switches are rejected", () => {
  const state = setTeam(createInitialState(teams), 0, importedTeam());
  const duplicate = structuredClone(state);
  duplicate.sides[0].players[2] = structuredClone(duplicate.sides[0].players[1]);
  assert.throws(() => validateTactic(duplicate, teams), /duplicate/i);
  const badKit = structuredClone(state);
  badKit.sides[0].team_data.kits[0].colors[0] = [500, 0, 0];
  assert.throws(() => validateTactic(badKit, teams), /color/i);
  const badSwitch = structuredClone(state);
  badSwitch.sides[0].players[5].switch_pair.after.name = "Other";
  assert.throws(() => validateTactic(badSwitch, teams), /substitution/i);
  const invalidLocation = structuredClone(state);
  invalidLocation.sides[0].players[0].x_m = Number.POSITIVE_INFINITY;
  assert.throws(() => validateTactic(invalidLocation, teams), /player X/);
});

test("history stores isolated snapshots and stops at the first state", () => {
  const first = createInitialState(teams);
  const second = movePlayer(first, 0, 1, 30, 30);
  const third = setBall(second, [50, 34]);
  const history = commit(commit(createHistory(first), second), third);
  assert.deepEqual(undo(history).present, second);
  assert.deepEqual(undo(undo(history)).present, first);
  assert.deepEqual(undo(undo(undo(history))).present, first);
  assert.deepEqual(first.ball, null);
});
