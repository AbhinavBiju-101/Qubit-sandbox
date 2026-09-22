/* ===================================================================
   bloch.js — draws a state vector on a Bloch sphere using a simple
   fixed-angle oblique projection. Good enough to see theta/phi move;
   not a physically-accurate 3D renderer, and it doesn't need to be.

   Depth convention: of the three sphere axes, only Y gets pushed
   diagonally by the projection (X and Z stay true-length, in the
   screen plane) — so "in front of" vs. "behind" the sphere is exactly
   the sign of the point's Y-coordinate. Y < 0 is drawn dashed/faded;
   Y >= 0 is drawn solid. That's the only depth cue this projection
   needs, and it falls out of the math rather than being guessed.
=================================================================== */

const BLOCH_TILT = 28 * Math.PI / 180; // viewing tilt for the "depth" axis

function blochSphereToXYZ(theta, phi) {
  return {
    x: Math.sin(theta) * Math.cos(phi),
    y: Math.sin(theta) * Math.sin(phi),
    z: Math.cos(theta),
  };
}

function blochProject3(x, y, z, R) {
  const sx = R * (x + y * Math.sin(BLOCH_TILT) * 0.55);
  const sy = -R * z + R * y * Math.cos(BLOCH_TILT) * 0.32;
  return { sx, sy };
}

function blochProject(theta, phi, R) {
  const { x, y, z } = blochSphereToXYZ(theta, phi);
  return blochProject3(x, y, z, R);
}

/**
 * Creates a Bloch sphere widget inside the given SVG element.
 * svgEl: an <svg> with a viewBox already set, roughly square.
 */
function createBlochWidget(svgEl) {
  const ns = 'http://www.w3.org/2000/svg';
  const vb = svgEl.viewBox.baseVal;
  const cx = vb.width / 2, cy = vb.height / 2;
  const R = Math.min(vb.width, vb.height) * 0.34;

  function el(tag, attrs) {
    const e = document.createElementNS(ns, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }
  function label(pt, text, opts) {
    const t = el('text', Object.assign({
      x: pt.sx, y: pt.sy, fill: 'var(--text-faint)',
      'font-family': 'var(--font-mono)', 'font-size': 12,
      'text-anchor': 'middle',
    }, opts || {}));
    t.textContent = text;
    return t;
  }

  svgEl.innerHTML = '';
  const g = el('g', { transform: `translate(${cx},${cy})` });
  svgEl.appendChild(g);

  // equator ellipse (depth-squashed circle)
  g.appendChild(el('ellipse', {
    cx: 0, cy: 0, rx: R, ry: R * Math.cos(BLOCH_TILT) * 0.32 + R * 0.02,
    fill: 'none', stroke: 'var(--line-bright)', 'stroke-width': 1, 'stroke-dasharray': '3 4'
  }));
  // outer sphere silhouette
  g.appendChild(el('circle', { cx: 0, cy: 0, r: R, fill: 'none', stroke: 'var(--line-bright)', 'stroke-width': 1.2 }));

  // ---- reference axes: Z (polar), X, Y — each with pole markers and
  // ket labels, so the six cardinal states are always visible even
  // before any vector is drawn. ----
  const Z_TOP = blochProject(0, 0, R), Z_BOT = blochProject(Math.PI, 0, R);
  const X_POS = blochProject(Math.PI/2, 0, R), X_NEG = blochProject(Math.PI/2, Math.PI, R);
  const Y_POS = blochProject(Math.PI/2, Math.PI/2, R), Y_NEG = blochProject(Math.PI/2, -Math.PI/2, R);

  g.appendChild(el('line', { x1: Z_TOP.sx, y1: Z_TOP.sy, x2: Z_BOT.sx, y2: Z_BOT.sy, stroke: 'var(--line)', 'stroke-width': 1 }));
  g.appendChild(el('line', { x1: X_NEG.sx, y1: X_NEG.sy, x2: X_POS.sx, y2: X_POS.sy, stroke: 'var(--line)', 'stroke-width': 1 }));
  // Y axis is the depth axis — its negative half is "behind" by this
  // projection's own convention (matches the live vector's own
  // dashing rule below), so it's the one axis line drawn in two
  // dashed/solid halves rather than one plain line.
  g.appendChild(el('line', { x1: 0, y1: 0, x2: Y_POS.sx, y2: Y_POS.sy, stroke: 'var(--line)', 'stroke-width': 1 }));
  g.appendChild(el('line', { x1: 0, y1: 0, x2: Y_NEG.sx, y2: Y_NEG.sy, stroke: 'var(--line)', 'stroke-width': 1, 'stroke-dasharray': '2 3', opacity: 0.6 }));

  [[Z_TOP,'|0⟩',-10,-6],[Z_BOT,'|1⟩',-10,16],[X_POS,'|+⟩',14,4],[X_NEG,'|−⟩',-16,4],
   [Y_POS,'|+i⟩',16,-4],[Y_NEG,'|−i⟩',-18,10]].forEach(([pt, text, dx, dy]) => {
    g.appendChild(el('circle', { cx: pt.sx, cy: pt.sy, r: 2.5, fill: 'var(--text-faint)' }));
    g.appendChild(label({ sx: pt.sx + dx, sy: pt.sy + dy }, text, { 'font-size': 12, fill: 'var(--text-faint)' }));
  });

  // ---- projection ("shadow") guide lines for the live state vector:
  // a drop-line from the tip down to the equatorial plane (shows the
  // z/theta component), and a line from the origin out to that same
  // foot point (shows the phi direction in-plane) — the usual
  // textbook-diagram way of reading theta and phi off a drawn vector. ----
  const dropLine = el('line', { x1:0, y1:0, x2:0, y2:0, stroke:'var(--text-faint)', 'stroke-width':1, 'stroke-dasharray':'2 3', opacity:0.7 });
  const shadowLine = el('line', { x1:0, y1:0, x2:0, y2:0, stroke:'var(--text-faint)', 'stroke-width':1, 'stroke-dasharray':'2 3', opacity:0.7 });
  const footDot = el('circle', { cx:0, cy:0, r:3, fill:'none', stroke:'var(--text-faint)', 'stroke-width':1.2 });
  g.appendChild(dropLine); g.appendChild(shadowLine); g.appendChild(footDot);

  // state vector line + tip dot
  const vecLine = el('line', { x1: 0, y1: 0, x2: 0, y2: -R, stroke: 'var(--copper)', 'stroke-width': 2.4, 'stroke-linecap': 'round' });
  const tip = el('circle', { cx: 0, cy: -R, r: 6, fill: 'var(--copper)' });
  const tipGlow = el('circle', { cx: 0, cy: -R, r: 11, fill: 'var(--copper)', opacity: 0.18 });
  g.appendChild(vecLine); g.appendChild(tipGlow); g.appendChild(tip);

  function set(theta, phi, mag) {
    const m = (typeof mag === 'number') ? mag : 1;
    const { x, y, z } = blochSphereToXYZ(theta, phi);
    const tipPt = blochProject3(x * m, y * m, z * m, R);
    const footPt = blochProject3(x * m, y * m, 0, R);

    vecLine.setAttribute('x2', tipPt.sx); vecLine.setAttribute('y2', tipPt.sy);
    tip.setAttribute('cx', tipPt.sx); tip.setAttribute('cy', tipPt.sy);
    tipGlow.setAttribute('cx', tipPt.sx); tipGlow.setAttribute('cy', tipPt.sy);

    // Behind the sphere (Y < 0, this projection's own depth rule): fade
    // and dash the vector so it visually recedes, exactly like the
    // reference Y-axis's own back half above.
    const behind = y < -1e-6;
    vecLine.setAttribute('stroke-dasharray', behind ? '5 4' : 'none');
    vecLine.setAttribute('opacity', behind ? 0.55 : 1);
    tip.setAttribute('opacity', behind ? 0.55 : 1);
    tipGlow.setAttribute('opacity', behind ? 0.10 : 0.18);

    dropLine.setAttribute('x2', tipPt.sx); dropLine.setAttribute('y2', tipPt.sy);
    dropLine.setAttribute('x1', footPt.sx); dropLine.setAttribute('y1', footPt.sy);
    shadowLine.setAttribute('x2', footPt.sx); shadowLine.setAttribute('y2', footPt.sy);
    footDot.setAttribute('cx', footPt.sx); footDot.setAttribute('cy', footPt.sy);
    // Hide the guide lines right at the poles, where the "shadow" on
    // the equatorial plane collapses to the origin and adds nothing.
    const nearPole = Math.sin(theta) < 0.03;
    dropLine.setAttribute('opacity', nearPole ? 0 : 0.7);
    shadowLine.setAttribute('opacity', nearPole ? 0 : 0.7);
    footDot.setAttribute('opacity', nearPole ? 0 : 0.7);
  }

  set(0, 0);
  return { set, R, cx, cy };
}
