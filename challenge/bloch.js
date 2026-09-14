/* ===================================================================
   bloch.js — draws a state vector on a Bloch sphere using a simple
   fixed-angle oblique projection. Good enough to see theta/phi move;
   not a physically-accurate 3D renderer, and it doesn't need to be.
=================================================================== */

const BLOCH_TILT = 28 * Math.PI / 180; // viewing tilt for the "depth" axis

function blochProject(theta, phi, R) {
  // sphere coords, z = polar axis (|0> at +z)
  const x = Math.sin(theta) * Math.cos(phi);
  const y = Math.sin(theta) * Math.sin(phi);
  const z = Math.cos(theta);
  // oblique projection: depth axis (y) pushed up-right and squashed
  const sx = R * (x + y * Math.sin(BLOCH_TILT) * 0.55);
  const sy = -R * z + R * y * Math.cos(BLOCH_TILT) * 0.32;
  return { sx, sy };
}

/**
 * Creates a Bloch sphere widget inside the given SVG element.
 * svgEl: an <svg> with a viewBox already set, roughly square.
 */
function createBlochWidget(svgEl) {
  const ns = 'http://www.w3.org/2000/svg';
  const vb = svgEl.viewBox.baseVal;
  const cx = vb.width / 2, cy = vb.height / 2;
  const R = Math.min(vb.width, vb.height) * 0.36;

  function el(tag, attrs) {
    const e = document.createElementNS(ns, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
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
  // polar axis
  g.appendChild(el('line', { x1: 0, y1: -R, x2: 0, y2: R, stroke: 'var(--line)', 'stroke-width': 1 }));
  // pole labels
  const t0 = el('text', { x: 6, y: -R - 8, fill: 'var(--text-muted)', 'font-family': 'var(--font-mono)', 'font-size': 13 });
  t0.textContent = '|0⟩'; g.appendChild(t0);
  const t1 = el('text', { x: 6, y: R + 20, fill: 'var(--text-muted)', 'font-family': 'var(--font-mono)', 'font-size': 13 });
  t1.textContent = '|1⟩'; g.appendChild(t1);

  // state vector line + tip dot
  const vecLine = el('line', { x1: 0, y1: 0, x2: 0, y2: -R, stroke: 'var(--copper)', 'stroke-width': 2.4, 'stroke-linecap': 'round' });
  const tip = el('circle', { cx: 0, cy: -R, r: 6, fill: 'var(--copper)' });
  const tipGlow = el('circle', { cx: 0, cy: -R, r: 11, fill: 'var(--copper)', opacity: 0.18 });
  g.appendChild(vecLine); g.appendChild(tipGlow); g.appendChild(tip);

  function set(theta, phi, mag) {
    const m = (typeof mag === 'number') ? mag : 1;
    const { sx, sy } = blochProject(theta, phi, R * m);
    vecLine.setAttribute('x2', sx); vecLine.setAttribute('y2', sy);
    tip.setAttribute('cx', sx); tip.setAttribute('cy', sy);
    tipGlow.setAttribute('cx', sx); tipGlow.setAttribute('cy', sy);
  }

  set(0, 0);
  return { set, R, cx, cy };
}
