/* Fluid — Apple-style fluid motion engine (vanilla, zero deps).
 *
 * A single rAF loop drives a small set of springs. A spring always animates
 * from the current on-screen value, can be re-targeted mid-flight (so motion
 * is interruptible), and carries velocity through a re-target (so a reversal
 * never hits a velocity "brick wall").
 *
 * Presets mirror Apple's UI-facing parameters:
 *   default  -> damping 1.0 (critically damped), response 0.35
 *   snappy   -> damping 1.0, response 0.26
 *   momentum -> damping 0.8,  response 0.35  (slight overshoot, for flicks)
 */
(function () {
    "use strict";

    // element -> { cur, vel, target, k, c, last, onComplete }
    const active = new Map();
    const AXES = ["x", "y", "scale", "opacity"];
    let ticking = false;

    function readCurrent(el, from, existing) {
        if (existing) {
            return { x: existing.cur.x, y: existing.cur.y, scale: existing.cur.scale, opacity: existing.cur.opacity };
        }
        const cs = getComputedStyle(el);
        return {
            x: from && from.x !== undefined ? from.x : 0,
            y: from && from.y !== undefined ? from.y : 0,
            scale: from && from.scale !== undefined ? from.scale : 1,
            opacity: from && from.opacity !== undefined ? from.opacity : (cs.opacity ? parseFloat(cs.opacity) : 1)
        };
    }

    function write(el, c) {
        el.style.transform = "translate3d(" + c.x + "px," + c.y + "px,0) scale(" + c.scale + ")";
        el.style.opacity = "" + Math.min(1, Math.max(0, c.opacity));
    }

    function stepState(st, dt) {
        for (const key of AXES) {
            // Semi-implicit Euler with small fixed slices keeps the spring stable
            // when a frame stalls or the browser briefly drops FPS.
            const accel = -st.k * (st.cur[key] - st.target[key]) - st.c * st.vel[key];
            st.vel[key] += accel * dt;
            st.cur[key] += st.vel[key] * dt;
        }
    }

    function tick(now) {
        for (const [el, st] of active) {
            const elapsed = ((now - (st.last || now)) / 1000) || 0.016;
            st.last = now;
            let remaining = Math.min(elapsed, 0.064);
            while (remaining > 0) {
                const dt = Math.min(remaining, 0.016);
                stepState(st, dt);
                remaining -= dt;
            }
            write(el, st.cur);
            const settled =
                Math.abs(st.target.x - st.cur.x) < 0.002 &&
                Math.abs(st.target.y - st.cur.y) < 0.002 &&
                Math.abs(st.target.scale - st.cur.scale) < 0.0008 &&
                Math.abs(st.target.opacity - st.cur.opacity) < 0.002 &&
                Math.abs(st.vel.x) < 0.02 && Math.abs(st.vel.y) < 0.02 &&
                Math.abs(st.vel.scale) < 0.001 && Math.abs(st.vel.opacity) < 0.001;
            if (settled) {
                write(el, st.target);
                active.delete(el);
                if (st.onComplete) st.onComplete();
            }
        }
        if (active.size > 0) {
            requestAnimationFrame(tick);
        } else {
            ticking = false;
        }
    }

    function ensureTicking() {
        if (!ticking) {
            ticking = true;
            requestAnimationFrame(tick);
        }
    }

    function physics(opts) {
        const response = opts.response == null ? 0.35 : opts.response;
        const damping = opts.damping == null ? 1.0 : opts.damping;
        const omega = 2 * Math.PI / Math.max(response, 0.001);
        return { k: omega * omega, c: 2 * damping * omega };
    }

    function animate(el, to, opts) {
        if (!el) return emptyHandle();
        opts = opts || {};
        const existing = active.get(el);

        if (existing) {
            // Interruptible re-target: continue from the live value/velocity.
            for (const key of AXES) if (to[key] !== undefined) existing.target[key] = to[key];
            if (opts.velocity) {
                existing.vel.x += opts.velocity.x || 0;
                existing.vel.y += opts.velocity.y || 0;
            }
            return handle(existing);
        }

        const cur = readCurrent(el, opts.from, null);
        const ph = animate.paramsFor(opts);
        const st = {
            cur: { x: cur.x, y: cur.y, scale: cur.scale, opacity: cur.opacity },
            vel: { x: opts.velocity ? opts.velocity.x || 0 : 0,
                   y: opts.velocity ? opts.velocity.y || 0 : 0,
                   scale: 0, opacity: 0 },
            target: { x: to.x !== undefined ? to.x : cur.x,
                      y: to.y !== undefined ? to.y : cur.y,
                      scale: to.scale !== undefined ? to.scale : cur.scale,
                      opacity: to.opacity !== undefined ? to.opacity : cur.opacity },
            k: ph.k, c: ph.c, last: null,
            onComplete: opts.onComplete
        };
        active.set(el, st);
        ensureTicking();
        return handle(st);
    }
    animate.paramsFor = (o) => {
        const damping = o.damping == null ? 1.0 : o.damping;
        const response = o.response == null ? 0.35 : o.response;
        const omega = 2 * Math.PI / Math.max(response, 0.001);
        return { k: omega * omega, c: 2 * damping * omega };
    };

    function handle(st) {
        return {
            retarget(next) {
                for (const key of AXES) if (next[key] !== undefined) st.target[key] = next[key];
            },
            stop() {
                const entry = [...active.entries()].find(([, value]) => value === st);
                if (entry) active.delete(entry[0]);
            }
        };
    }
    function emptyHandle() {
        return { retarget() {}, stop() {} };
    }

    // Momentum projection — Apple's exponential-decay form, used to pick the
    // resting point a flick is thrown at (§6).
    function project(velocity, decelerationRate) {
        const d = decelerationRate == null ? 0.998 : decelerationRate;
        return (velocity / 1000) * d / (1 - d);
    }

    // Relative velocity normalization for handoff into a spring, §5.
    function relativeVelocity(gestureVelocity, remaining) {
        if (!remaining) return 0;
        return gestureVelocity / remaining;
    }

    // Progressive resistance at a boundary, §9.
    function rubberband(overshoot, dimension, constant) {
        const c = constant == null ? 0.55 : constant;
        return (overshoot * dimension * c) / (dimension + c * Math.abs(overshoot));
    }

    // Light haptics, mobile only, guarded, §13 utility (overuse is discouraged).
    function vibrate(duration) {
        if (typeof navigator !== "undefined" && navigator.vibrate) navigator.vibrate(duration);
    }
    const haptic = { tap() { vibrate(12); }, snap() { vibrate(24); } };

    window.Fluid = {
        animate,
        project,
        relativeVelocity,
        rubberband,
        haptic,
        _activeCount() { return active.size; }
    };
})();
