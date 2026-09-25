// A minimal spring engine implementing the physics described in Apple's
// "Designing Fluid Interfaces" (WWDC 2018): motion that starts from the
// current on-screen value, carries velocity, and can be grabbed and
// redirected at any instant. No external animation library - this is the
// full physics loop, driven by requestAnimationFrame.
//
// Parameters are Apple's own designer-friendly pair (not the raw
// mass/stiffness/damping triplet):
//   damping  - 1.0 = critically damped (no overshoot). <1.0 = bouncy.
//   response - how many seconds it takes to reach the target. NOT a fixed
//              duration - a spring has no fixed duration, this just shapes
//              the physics constants.

export class Spring {
  constructor({
    position = 0,
    target = 0,
    damping = 1.0,
    response = 0.35,
    mass = 1,
    onUpdate = null,
    onSettle = null,
  } = {}) {
    this.position = position;
    this.velocity = 0;
    this.target = target;
    this.mass = mass;
    this.onUpdate = onUpdate;
    this.onSettle = onSettle;
    this.setDampingResponse(damping, response);
    this._raf = null;
    this._lastT = null;
  }

  setDampingResponse(damping, response) {
    const angularFrequency = (2 * Math.PI) / Math.max(response, 0.001);
    this.stiffness = this.mass * angularFrequency * angularFrequency;
    this.damping = (4 * Math.PI * damping * this.mass) / Math.max(response, 0.001);
  }

  // Retarget at any instant - this IS the interruptibility. Position and
  // velocity are whatever they currently are; nothing resets, so a spring
  // grabbed mid-flight reverses smoothly instead of jumping.
  setTarget(target, { velocity } = {}) {
    this.target = target;
    if (velocity !== undefined) this.velocity = velocity;
    this._ensureRunning();
  }

  // Move instantly with no animation (e.g. "attach" the value to a pointer
  // during a drag) - keeps velocity so a later setTarget() hands off cleanly.
  jumpTo(position, velocity = 0) {
    this.stop();
    this.position = position;
    this.velocity = velocity;
    this.target = position;
    if (this.onUpdate) this.onUpdate(this.position);
  }

  stop() {
    if (this._raf) cancelAnimationFrame(this._raf);
    this._raf = null;
    this._lastT = null;
  }

  get isSettled() {
    return Math.abs(this.position - this.target) < 0.01 && Math.abs(this.velocity) < 0.01;
  }

  _ensureRunning() {
    if (this._raf) return;
    this._lastT = performance.now();
    const step = (t) => {
      const dt = Math.min((t - this._lastT) / 1000, 1 / 30); // clamp for tab-switch hitches
      this._lastT = t;

      const displacement = this.position - this.target;
      const springForce = -this.stiffness * displacement;
      const dampingForce = -this.damping * this.velocity;
      const acceleration = (springForce + dampingForce) / this.mass;

      this.velocity += acceleration * dt;
      this.position += this.velocity * dt;

      if (this.onUpdate) this.onUpdate(this.position);

      if (this.isSettled) {
        this.position = this.target;
        this.velocity = 0;
        if (this.onUpdate) this.onUpdate(this.position);
        this._raf = null;
        this._lastT = null;
        if (this.onSettle) this.onSettle();
        return;
      }
      this._raf = requestAnimationFrame(step);
    };
    this._raf = requestAnimationFrame(step);
  }
}

// Momentum projection (§6, "Designing Fluid Interfaces") - given a release
// velocity, where would this gesture "land" if it kept decelerating like a
// real flick/scroll? Used to pick which snap point a drag resolves to,
// instead of just looking at where the finger happened to let go.
export function project(velocity, decelerationRate = 0.998) {
  return ((velocity / 1000) * decelerationRate) / (1 - decelerationRate);
}

// Rubber-band resistance past a boundary (§9) - progressive resistance
// instead of a hard stop, so dragging past the top of a sheet still feels
// alive rather than frozen.
export function rubberband(overshoot, dimension, constant = 0.55) {
  return (overshoot * dimension * constant) / (dimension + constant * Math.abs(overshoot));
}

// Tracks the last few samples of a dragged value so we can compute a
// release velocity (§2) - a single last-frame delta is too noisy.
export class VelocityTracker {
  constructor(historyMs = 100) {
    this.historyMs = historyMs;
    this.samples = [];
  }
  push(value, t = performance.now()) {
    this.samples.push({ value, t });
    const cutoff = t - this.historyMs;
    while (this.samples.length > 2 && this.samples[0].t < cutoff) this.samples.shift();
  }
  velocity() {
    if (this.samples.length < 2) return 0;
    const a = this.samples[0];
    const b = this.samples[this.samples.length - 1];
    const dt = (b.t - a.t) / 1000;
    if (dt <= 0) return 0;
    return (b.value - a.value) / dt; // units per second
  }
  reset() {
    this.samples = [];
  }
}
