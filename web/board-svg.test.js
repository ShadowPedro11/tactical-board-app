import assert from 'node:assert/strict';
import test from 'node:test';

import { renderBoard } from './board-svg.js';

class FakeNode {
  constructor(tagName, ownerDocument) {
    this.tagName = tagName;
    this.ownerDocument = ownerDocument;
    this.children = [];
    this.attributes = {};
    this.textContent = '';
    this.clientWidth = 0;
  }

  appendChild(node) {
    this.children.push(node);
    return node;
  }

  replaceChildren(...nodes) {
    this.children = nodes;
  }

  setAttribute(name, value) {
    this.attributes[name] = value;
  }

  getBoundingClientRect() {
    return { width: this.clientWidth };
  }
}

class FakeDocument {
  createElementNS(_namespace, name) {
    return new FakeNode(name, this);
  }
}

function surface(width = 1150) {
  const doc = new FakeDocument();
  const svg = doc.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.clientWidth = width;
  return svg;
}

function descendants(node, predicate) {
  return node.children.flatMap(child => [
    ...(predicate(child) ? [child] : []),
    ...descendants(child, predicate),
  ]);
}

function fixture() {
  const teams = [
    {
      id: 'home', name: 'Home',
      kits: [{ name: 'Home shirt', pattern: 'stripes', colors: [[16, 36, 92], [255, 255, 255]] }],
      gk_kit: { name: 'Goalkeeper', pattern: 'solid', colors: [[255, 230, 35]] },
    },
    {
      id: 'away', name: 'Away',
      kits: [{ name: 'Away shirt', pattern: 'hoops', colors: [[230, 20, 20], [255, 255, 255]] }],
      gk_kit: { name: 'Goalkeeper', pattern: 'solid', colors: [[18, 18, 18]] },
    },
  ];
  const players = side => Array.from({ length: 11 }, (_, slot) => ({
    number: slot + 1,
    name: `Player ${side}-${slot}`,
    position: slot === 0 ? 'GK' : 'DF',
    x_m: side === 0 ? 4 + slot * 4 : 101 - slot * 4,
    y_m: 8 + slot * 5,
  }));
  const state = {
    version: 1,
    sides: [
      { team_id: 'home', kit_index: 0, formation: '4-4-2', players: players(0) },
      { team_id: 'away', kit_index: 0, formation: '4-4-2', players: players(1) },
    ],
    arrows: [[[12, 20], [32, 24]]],
    ball: [52.5, 34],
  };
  state.sides[0].players[2].switch_pair = {
    before: { name: 'Player 0-2', number: 3, position: 'DF' },
    after: { name: 'Substitute', number: 23, position: 'MF' },
    minute: 70,
  };
  state.sides[0].players[2].switch_active = false;
  return { teams, state };
}

test('renders pitch geometry, annotations and 22 interactive players', () => {
  const svg = surface();
  const { state, teams } = fixture();
  renderBoard(svg, state, teams, { mode: 'arrow', selectedSlot: { side: 0, slot: 2 } });

  assert.equal(svg.attributes.viewBox, '-5 -5 115 78');
  assert.equal(svg.attributes['data-mode'], 'arrow');
  assert.equal(descendants(svg, node => node.attributes.class === 'player-token').length, 22);
  assert.equal(descendants(svg, node => node.attributes['data-player'] === '1').length, 22);
  assert.equal(descendants(svg, node => node.attributes.class === 'board-background').length, 1);
  assert.equal(descendants(svg, node => node.tagName === 'rect' &&
    node.attributes.width === '105' && node.attributes.height === '68').length, 2);
  assert.equal(descendants(svg, node => node.attributes.class === 'switch-badge').length, 1);
  assert.equal(descendants(svg, node => node.attributes['data-switch'] === '1').length, 1);
  assert.equal(descendants(svg, node => node.tagName === 'line' &&
    node.attributes['marker-end']?.includes('arrowhead')).length, 1);
  const selectedToken = descendants(svg, node => node.attributes['data-side'] === '0' &&
    node.attributes['data-slot'] === '2')[0];
  assert.equal(selectedToken.attributes.role, 'button');
  assert.equal(descendants(selectedToken, node => node.tagName === 'circle' &&
    node.attributes.stroke === '#fff165').length, 1);
});

test('draws kit patterns once, outlines numbers, and does not mutate the tactic', () => {
  const svg = surface();
  const { state, teams } = fixture();
  const original = structuredClone(state);
  renderBoard(svg, state, teams, { draftArrow: [[25, 25], [40, 40]] });

  const patterns = descendants(svg, node => node.tagName === 'pattern');
  assert.equal(patterns.length, 2);
  assert.equal(new Set(patterns.map(node => node.attributes.id)).size, 2);
  const numbers = descendants(svg, node => node.tagName === 'text' &&
    node.attributes['paint-order'] === 'stroke fill');
  assert.ok(numbers.length >= 22);
  assert.ok(numbers.some(node => node.attributes['stroke-width']));
  assert.deepEqual(state, original);
});

test('hides names on narrow screens and uses imported team data', () => {
  const svg = surface(360);
  const { state, teams } = fixture();
  state.sides[1].team_id = 'zerozero-123-away';
  state.sides[1].team_data = {
    id: 'zerozero-123-away', name: 'Imported Team',
    kits: [{ name: 'Match', pattern: 'solid', colors: [[12, 70, 180]] }],
    gk_kit: { name: 'GK', pattern: 'solid', colors: [[200, 180, 20]] },
  };
  renderBoard(svg, state, teams);

  const imported = descendants(svg, node => node.attributes['data-side'] === '1' &&
    node.attributes['data-slot'] === '1')[0];
  assert.match(imported.attributes['aria-label'], /Imported Team/);
  assert.equal(descendants(imported, node => node.tagName === 'circle' &&
    node.attributes.fill === '#0c46b4').length, 1);
  assert.equal(descendants(svg, node => node.tagName === 'text').length, 22);
});

test('renders both sleeve colors from bundled kit patterns', () => {
  const svg = surface();
  const { state, teams } = fixture();
  teams[0].kits[0].pattern = 'sleeves_plain_2_col-2';
  renderBoard(svg, state, teams);
  const pattern = descendants(svg, node => node.tagName === 'pattern' &&
    node.attributes.id?.endsWith('kit-0-field'))[0];
  assert.ok(pattern);
  assert.equal(descendants(pattern, node => node.tagName === 'rect' &&
    node.attributes.fill === '#ffffff').length, 2);
});
