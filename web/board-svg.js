/** Render the tactical board directly into an SVG element.
 *
 * The tactic document stores positions in pitch metres, so SVG's viewBox is
 * also expressed in metres. Browser layout can resize the board freely without
 * changing the saved coordinates.
 */

const SVG_NS = 'http://www.w3.org/2000/svg';
const PITCH_LENGTH = 105;
const PITCH_WIDTH = 68;
const PENALTY_TOP = (PITCH_WIDTH - 40.32) / 2;
const GOAL_AREA_TOP = (PITCH_WIDTH - 18.32) / 2;
const GOAL_TOP = (PITCH_WIDTH - 7.32) / 2;
const PENALTY_ARC_HALF_HEIGHT = Math.sqrt(9.15 ** 2 - 5.5 ** 2);
const boardIds = new WeakMap();
let nextBoardId = 0;

function add(parent, tag, attrs = {}, content) {
  const node = parent.ownerDocument.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value !== undefined && value !== null) node.setAttribute(name, String(value));
  }
  if (content !== undefined) node.textContent = String(content);
  parent.appendChild(node);
  return node;
}

function color(value, fallback = '#839a89') {
  if (typeof value === 'string' && /^#[0-9a-f]{3}(?:[0-9a-f]{3})?$/i.test(value)) return value;
  if (Array.isArray(value) && value.length === 3 &&
      value.every(channel => Number.isInteger(channel) && channel >= 0 && channel <= 255)) {
    return `#${value.map(channel => channel.toString(16).padStart(2, '0')).join('')}`;
  }
  return fallback;
}

function luminance(hex) {
  const expanded = hex.length === 4
    ? `#${[...hex.slice(1)].map(digit => digit + digit).join('')}` : hex;
  const rgb = [1, 3, 5].map(index => parseInt(expanded.slice(index, index + 2), 16));
  return rgb[0] * 0.299 + rgb[1] * 0.587 + rgb[2] * 0.114;
}

function kitFill(defs, id, kit) {
  const colors = Array.isArray(kit?.colors) ? kit.colors : [];
  const base = color(colors[0]);
  const accent = color(colors[1], base);
  if (colors.length < 2 || kit?.pattern === 'solid') return base;

  const pattern = add(defs, 'pattern', {
    id, patternUnits: 'objectBoundingBox', patternContentUnits: 'objectBoundingBox',
    width: 1, height: 1,
  });
  add(pattern, 'rect', { x: 0, y: 0, width: 1, height: 1, fill: base });
  const kind = String(kit?.pattern || '').toLowerCase();
  if (kind === 'halves') {
    add(pattern, 'rect', { x: 0.5, y: 0, width: 0.5, height: 1, fill: accent });
  } else if (kind.includes('sleeves')) {
    add(pattern, 'rect', { x: 0, y: 0, width: 0.23, height: 1, fill: accent });
    add(pattern, 'rect', { x: 0.77, y: 0, width: 0.23, height: 1, fill: accent });
  } else if (kind === 'hoops' || kind.includes('horizontal')) {
    for (let i = 1; i < 6; i += 2) {
      add(pattern, 'rect', { x: 0, y: i / 6, width: 1, height: 1 / 6, fill: accent });
    }
  } else if (kind === 'vertical_stripes' || kind.includes('vertical-2-stripes')) {
    add(pattern, 'rect', { x: 2 / 7, y: 0, width: 1 / 7, height: 1, fill: accent });
    add(pattern, 'rect', { x: 4 / 7, y: 0, width: 1 / 7, height: 1, fill: accent });
  } else if (kind === 'stripes' || kind.includes('stripe')) {
    for (let i = 1; i < 6; i += 2) {
      add(pattern, 'rect', { x: i / 6, y: 0, width: 1 / 6, height: 1, fill: accent });
    }
  }
  return `url(#${id})`;
}

function paintPitch(svg) {
  const pitch = add(svg, 'g', { class: 'pitch', 'pointer-events': 'none' });
  add(pitch, 'rect', { x: 0, y: 0, width: PITCH_LENGTH, height: PITCH_WIDTH, fill: '#2e7d42' });
  for (let i = 0; i < 10; i += 2) {
    add(pitch, 'rect', {
      x: i * PITCH_LENGTH / 10, y: 0,
      width: PITCH_LENGTH / 10, height: PITCH_WIDTH, fill: '#ffffff', opacity: 0.035,
    });
  }
  const line = { fill: 'none', stroke: '#f5f6ee', 'stroke-width': 0.22 };
  add(pitch, 'rect', { ...line, x: 0, y: 0, width: PITCH_LENGTH, height: PITCH_WIDTH });
  add(pitch, 'line', { ...line, x1: PITCH_LENGTH / 2, y1: 0, x2: PITCH_LENGTH / 2, y2: PITCH_WIDTH });
  add(pitch, 'circle', { ...line, cx: PITCH_LENGTH / 2, cy: PITCH_WIDTH / 2, r: 9.15 });
  add(pitch, 'circle', { cx: PITCH_LENGTH / 2, cy: PITCH_WIDTH / 2, r: 0.28, fill: '#f5f6ee' });

  for (const right of [false, true]) {
    const edge = right ? PITCH_LENGTH : 0;
    const sign = right ? -1 : 1;
    add(pitch, 'rect', {
      ...line, x: right ? PITCH_LENGTH - 16.5 : 0, y: PENALTY_TOP,
      width: 16.5, height: 40.32,
    });
    add(pitch, 'rect', {
      ...line, x: right ? PITCH_LENGTH - 5.5 : 0, y: GOAL_AREA_TOP,
      width: 5.5, height: 18.32,
    });
    add(pitch, 'circle', { cx: edge + sign * 11, cy: 34, r: 0.28, fill: '#f5f6ee' });
    const arcX = edge + sign * 16.5;
    add(pitch, 'path', {
      ...line,
      d: `M ${arcX} ${34 - PENALTY_ARC_HALF_HEIGHT} A 9.15 9.15 0 0 ${right ? 0 : 1} ${arcX} ${34 + PENALTY_ARC_HALF_HEIGHT}`,
    });
    add(pitch, 'rect', {
      ...line, x: right ? PITCH_LENGTH : -2, y: GOAL_TOP,
      width: 2, height: 7.32,
    });
  }
  add(pitch, 'path', {
    ...line,
    d: 'M 1 0 A 1 1 0 0 1 0 1 M 104 0 A 1 1 0 0 0 105 1 ' +
       'M 0 67 A 1 1 0 0 1 1 68 M 105 67 A 1 1 0 0 0 104 68',
  });
}

function finitePoint(value) {
  return Array.isArray(value) && value.length === 2 &&
    value.every(Number.isFinite) && value[0] >= 0 && value[0] <= PITCH_LENGTH &&
    value[1] >= 0 && value[1] <= PITCH_WIDTH;
}

function paintAnnotations(svg, state, options, markerId) {
  const layer = add(svg, 'g', { class: 'annotations', 'pointer-events': 'none' });
  const arrows = Array.isArray(state?.arrows) ? [...state.arrows] : [];
  const draft = options.draftArrow;
  if (draft) arrows.push(draft);
  for (const arrow of arrows) {
    const start = Array.isArray(arrow) ? arrow[0] : arrow?.start;
    const end = Array.isArray(arrow) ? arrow[1] : arrow?.end;
    if (!finitePoint(start) || !finitePoint(end)) continue;
    add(layer, 'line', {
      x1: start[0], y1: start[1], x2: end[0], y2: end[1],
      stroke: '#ffdf54', 'stroke-width': 0.45, 'stroke-linecap': 'round',
      'marker-end': `url(#${markerId})`, opacity: arrow === draft ? 0.7 : 1,
    });
  }
  if (finitePoint(state?.ball)) {
    add(layer, 'circle', {
      cx: state.ball[0], cy: state.ball[1], r: 0.9,
      fill: '#f8f8f3', stroke: '#181c1a', 'stroke-width': 0.24,
    });
    add(layer, 'circle', { cx: state.ball[0], cy: state.ball[1], r: 0.27, fill: '#181c1a' });
  }
}

function selected(options, side, slot) {
  const value = options.selectedSlot;
  if (Array.isArray(value)) return (value[0] === side || value[0] === (side ? 'B' : 'A')) && value[1] === slot;
  if (typeof value === 'string') return value === `${side}:${slot}` || value === `${side ? 'B' : 'A'}:${slot}`;
  return value && (value.side === side || value.side === (side ? 'B' : 'A')) && value.slot === slot;
}

function paintSwitchBadge(token, radius, badgeRadius, player) {
  if (!player?.switch_pair) return;
  const x = radius + badgeRadius * 0.35;
  const y = -x;
  const badge = add(token, 'g', {
    class: 'switch-badge', 'data-switch': '1', role: 'button', tabindex: '0',
    'aria-label': `Switch ${player.name || 'player'} to ${
      (player.switch_active ? player.switch_pair.before : player.switch_pair.after)?.name || 'substitute'
    }`,
    transform: `translate(${x} ${y})`,
  });
  add(badge, 'circle', {
    r: badgeRadius + 0.13, fill: '#161d18',
  });
  add(badge, 'circle', {
    r: badgeRadius, fill: '#f5bd47',
  });
  const span = badgeRadius * 0.55;
  const rise = badgeRadius * 0.22;
  add(badge, 'path', {
    d: `M ${-span} ${-rise} H ${span} m ${-badgeRadius * 0.22} ${-rise} ` +
       `l ${badgeRadius * 0.22} ${rise} l ${-badgeRadius * 0.22} ${rise} ` +
       `M ${span} ${rise} H ${-span} m ${badgeRadius * 0.22} ${-rise} ` +
       `l ${-badgeRadius * 0.22} ${rise} l ${badgeRadius * 0.22} ${rise}`,
    fill: 'none', stroke: '#1b221c', 'stroke-width': Math.max(0.15, badgeRadius * 0.13),
    'stroke-linecap': 'round', 'stroke-linejoin': 'round',
  });
}

function paintPlayer(svg, defs, fillCache, state, teams, sideIndex, slot, options, sizing, prefix) {
  const side = state.sides[sideIndex];
  const player = side?.players?.[slot];
  if (!player || !Number.isFinite(player.x_m) || !Number.isFinite(player.y_m)) return;
  const team = side.team_data || teams.find(item => String(item.id) === String(side.team_id));
  const kit = slot === 0 ? team?.gk_kit : team?.kits?.[side.kit_index] || team?.kits?.[0];
  const fillId = `${prefix}-kit-${sideIndex}-${slot === 0 ? 'gk' : 'field'}`;
  if (!fillCache.has(fillId)) fillCache.set(fillId, kitFill(defs, fillId, kit));
  const fill = fillCache.get(fillId);
  const base = color(kit?.colors?.[0]);
  const light = luminance(base) < 140;
  const numberFill = light ? '#ffffff' : '#18211b';
  const numberStroke = light ? '#101810' : '#ffffff';
  const x = Math.max(0, Math.min(PITCH_LENGTH, player.x_m));
  const y = Math.max(0, Math.min(PITCH_WIDTH, player.y_m));
  const token = add(svg, 'g', {
    class: 'player-token', 'data-player': '1', 'data-side': sideIndex, 'data-slot': slot,
    transform: `translate(${x} ${y})`, role: 'button', tabindex: '0',
    'aria-label': `${team?.name || `Side ${sideIndex ? 'B' : 'A'}`}: #${player.number} ${player.name}`,
  });
  add(token, 'title', {}, `${team?.name || `Side ${sideIndex ? 'B' : 'A'}`}: #${player.number} ${player.name}`);
  // The transparent target keeps tokens easy to tap while the visible circle
  // retains a size close to the original board on both phones and desktops.
  add(token, 'circle', { r: Math.max(sizing.radius, sizing.hitRadius), fill: 'transparent' });
  if (selected(options, sideIndex, slot)) {
    add(token, 'circle', {
      r: sizing.radius + 0.5, fill: 'none', stroke: '#fff165', 'stroke-width': 0.35,
    });
  }
  add(token, 'circle', {
    r: sizing.radius, fill, stroke: '#162019', 'stroke-width': 0.25,
  });
  add(token, 'text', {
    x: 0, y: 0.08, 'text-anchor': 'middle', 'dominant-baseline': 'middle',
    fill: numberFill, stroke: numberStroke,
    'stroke-width': Math.max(0.32, sizing.numberSize * 0.27),
    'stroke-linejoin': 'round', 'paint-order': 'stroke fill',
    'font-family': 'Arial, system-ui, sans-serif', 'font-weight': 800,
    'font-size': sizing.numberSize, 'pointer-events': 'none',
  }, player.number);
  if (sizing.showNames) {
    add(token, 'text', {
      class: 'player-name',
      x: 0, y: sizing.radius + sizing.nameSize * 1.2,
      'text-anchor': 'middle', fill: '#ffffff', stroke: '#102016',
      'stroke-width': sizing.nameSize * 0.4, 'stroke-linejoin': 'round',
      'paint-order': 'stroke fill', 'font-family': 'Arial, system-ui, sans-serif',
      'font-weight': 700, 'font-size': sizing.nameSize,
      'pointer-events': 'none',
    }, player.name);
  }
  paintSwitchBadge(token, sizing.radius, sizing.badgeRadius, player);
}

/**
 * @param {SVGSVGElement} svg Existing SVG surface owned by the app.
 * @param {object} state Version 1 tactic JSON.
 * @param {Array<object>} teams Embedded club data; imported sides carry team_data.
 * @param {object} options mode, draftArrow, selectedSlot, and showNames.
 */
export function renderBoard(svg, state, teams, options = {}) {
  if (!svg?.ownerDocument || !Array.isArray(state?.sides) || state.sides.length !== 2) {
    throw new TypeError('renderBoard needs an SVG element and a two-sided tactic');
  }
  if (!boardIds.has(svg)) boardIds.set(svg, `board-${++nextBoardId}`);
  const prefix = boardIds.get(svg);
  svg.replaceChildren();
  svg.setAttribute('viewBox', '-5 -5 115 78');
  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  svg.setAttribute('aria-label', 'Football tactics board, 105 by 68 metres');
  svg.setAttribute('data-mode', options.mode || 'move');
  const defs = add(svg, 'defs');
  const markerId = `${prefix}-arrowhead`;
  const marker = add(defs, 'marker', {
    id: markerId, markerWidth: 2.6, markerHeight: 2.6,
    refX: 2.4, refY: 1.3, orient: 'auto', markerUnits: 'userSpaceOnUse',
  });
  add(marker, 'path', { d: 'M 0 0 L 2.6 1.3 L 0 2.6 z', fill: '#ffdf54' });

  const width = svg.getBoundingClientRect?.().width || svg.clientWidth || 1150;
  const pixelsPerMetre = Math.max(1, width / 115);
  const sizing = {
    radius: Math.max(10, Math.min(18, 1.3 * pixelsPerMetre)) / pixelsPerMetre,
    hitRadius: 20 / pixelsPerMetre,
    badgeRadius: Math.max(8, Math.min(11, 0.85 * pixelsPerMetre)) / pixelsPerMetre,
    numberSize: Math.max(12, Math.min(18, 1.5 * pixelsPerMetre)) / pixelsPerMetre,
    nameSize: Math.max(10, Math.min(14, 1.15 * pixelsPerMetre)) / pixelsPerMetre,
    showNames: options.showNames ?? width >= 680,
  };

  add(svg, 'rect', {
    x: -5, y: -5, width: 115, height: 78, fill: '#173d27',
    class: 'board-background',
  });
  paintPitch(svg);
  paintAnnotations(svg, state, options, markerId);
  const embedded = Array.isArray(teams) ? teams : [];
  const fillCache = new Map();
  for (let side = 0; side < 2; side += 1) {
    for (let slot = 0; slot < 11; slot += 1) {
      paintPlayer(svg, defs, fillCache, state, embedded, side, slot, options, sizing, prefix);
    }
  }
  return svg;
}
