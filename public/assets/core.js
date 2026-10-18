/* ============================================================
   CORE STILL — interactions
   ============================================================ */
(function () {
  "use strict";

  /* ---- header shrink on scroll ---- */
  var header = document.querySelector(".site-header");
  if (header) {
    window.addEventListener("scroll", function () {
      header.classList.toggle("scrolled", window.scrollY > 40);
    }, { passive: true });
  }

  /* ---- mobile nav ---- */
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.querySelector(".nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      toggle.classList.toggle("open");
      nav.classList.toggle("open");
    });
    nav.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function () {
        toggle.classList.remove("open");
        nav.classList.remove("open");
      });
    });
  }

  /* ---- scroll reveal ---- */
  var reveals = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          e.target.classList.add("in");
          io.unobserve(e.target);
        }
      });
    }, { threshold: 0.16 });
    reveals.forEach(function (el) { io.observe(el); });
  } else {
    reveals.forEach(function (el) { el.classList.add("in"); });
  }

  /* ---- count up ---- */
  function animateCount(el) {
    var target = parseFloat(el.dataset.count);
    var dur = 1600, start = null;
    var suffix = el.dataset.suffix || "";
    function step(ts) {
      if (!start) start = ts;
      var p = Math.min((ts - start) / dur, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      var val = target * eased;
      el.textContent = (target % 1 === 0 ? Math.round(val) : val.toFixed(1)) + suffix;
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  var counters = document.querySelectorAll("[data-count]");
  if (counters.length && "IntersectionObserver" in window) {
    var cio = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { animateCount(e.target); cio.unobserve(e.target); }
      });
    }, { threshold: 0.6 });
    counters.forEach(function (el) { cio.observe(el); });
  }

  /* ---- hero subtle parallax on grid ---- */
  var grids = document.querySelectorAll(".hero-grid");
  if (grids.length) {
    window.addEventListener("scroll", function () {
      var y = window.scrollY * 0.18;
      grids.forEach(function (g) { g.style.transform = "translateY(" + y + "px)"; });
    }, { passive: true });
  }

  /* ---- ecosystem loop: draw rings on scroll into view ---- */
  var loop = document.querySelector(".loop-svg");
  if (loop && "IntersectionObserver" in window) {
    var lio = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          loop.querySelectorAll(".ring").forEach(function (r) {
            var len = r.getTotalLength();
            r.style.strokeDasharray = len;
            r.style.strokeDashoffset = len;
            r.getBoundingClientRect(); // reflow
            r.style.transition = "stroke-dashoffset 2.4s cubic-bezier(0.22,1,0.36,1)";
            r.style.strokeDashoffset = 0;
          });
          lio.unobserve(loop);
        }
      });
    }, { threshold: 0.4 });
    lio.observe(loop);
  }

  /* ---- hero motion field: motion-capture style node network ---- */
  var canvas = document.querySelector(".hero-canvas");
  if (canvas && canvas.getContext) {
    var ctx = canvas.getContext("2d");
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var W = 0, H = 0, nodes = [], raf = null, running = false;
    var LINK = 150;            // link distance
    var SILVER = "184,188,194";

    function resize() {
      W = canvas.offsetWidth; H = canvas.offsetHeight;
      canvas.width = Math.floor(W * dpr);
      canvas.height = Math.floor(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var target = Math.round(Math.min(120, Math.max(38, (W * H) / 16000)));
      nodes = [];
      for (var i = 0; i < target; i++) {
        nodes.push({
          x: Math.random() * W,
          y: Math.random() * H,
          vx: (Math.random() - 0.5) * 0.22,
          vy: (Math.random() - 0.5) * 0.22,
          r: Math.random() * 1.4 + 0.6,
          a: Math.random() * 0.5 + 0.25,
          anchor: Math.random() < 0.12
        });
      }
    }

    function draw() {
      ctx.clearRect(0, 0, W, H);
      var i, j, a, b, dx, dy, d2, d, o;
      for (i = 0; i < nodes.length; i++) {
        a = nodes[i];
        a.x += a.vx; a.y += a.vy;
        if (a.x < 0 || a.x > W) a.vx *= -1;
        if (a.y < 0 || a.y > H) a.vy *= -1;
      }
      // links
      ctx.lineWidth = 1;
      for (i = 0; i < nodes.length; i++) {
        a = nodes[i];
        for (j = i + 1; j < nodes.length; j++) {
          b = nodes[j];
          dx = a.x - b.x; dy = a.y - b.y; d2 = dx * dx + dy * dy;
          if (d2 < LINK * LINK) {
            d = Math.sqrt(d2);
            o = (1 - d / LINK) * 0.18;
            ctx.strokeStyle = "rgba(" + SILVER + "," + o.toFixed(3) + ")";
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }
      // nodes
      for (i = 0; i < nodes.length; i++) {
        a = nodes[i];
        ctx.beginPath();
        ctx.arc(a.x, a.y, a.r, 0, 6.2832);
        if (a.anchor) {
          ctx.fillStyle = "rgba(255,255,255," + (a.a + 0.25).toFixed(3) + ")";
        } else {
          ctx.fillStyle = "rgba(" + SILVER + "," + a.a.toFixed(3) + ")";
        }
        ctx.fill();
      }
    }

    function loop() { draw(); raf = requestAnimationFrame(loop); }
    function start() { if (!running && !reduce) { running = true; loop(); } }
    function stop() { running = false; if (raf) cancelAnimationFrame(raf); raf = null; }

    resize();
    draw(); // paint first frame (also the static frame for reduced-motion)
    window.addEventListener("resize", function () { resize(); if (reduce) draw(); }, { passive: true });
    document.addEventListener("visibilitychange", function () { document.hidden ? stop() : start(); });

    if ("IntersectionObserver" in window) {
      var hio = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) { e.isIntersecting ? start() : stop(); });
      }, { threshold: 0 });
      hio.observe(canvas);
    } else { start(); }
  }
})();
