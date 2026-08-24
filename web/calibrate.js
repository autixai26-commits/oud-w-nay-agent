/* معايرة مواقع النقاط — SPEC القسم 4 والمرحلة 6.
   الإحداثيات نسب مئوية من أبعاد الصورة، فتصمد مع أي عرض شاشة. */
(function () {
  "use strict";

  var API = (window.OUD_CONFIG && window.OUD_CONFIG.apiBase) || "";
  var q = new URLSearchParams(location.search);
  if (q.get("api")) { API = q.get("api"); }

  var TOKEN = "";
  var HALLS = null;      // الحالة المعروضة (قابلة للتعديل)
  var ORIGINAL = null;   // نسخة كما جاءت من قاعدة البيانات
  var ACTIVE = "outdoor";
  var HALL_AR = { outdoor: "الصالة الخارجية", main: "الصالة الكبيرة",
                  narrow: "الصالة الضيقة" };

  function $(id) { return document.getElementById(id); }
  function show(id) { $(id).classList.remove("hidden"); }
  function hide(id) { $(id).classList.add("hidden"); }

  /* --------------------------------------------------------- الدخول */
  $("gate-form").onsubmit = function (e) {
    e.preventDefault();
    $("gate-btn").disabled = true;
    hide("gate-err");
    fetch(API + "/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: $("pw").value })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        $("gate-btn").disabled = false;
        if (!d.ok) { return show("gate-err"); }
        TOKEN = d.token;
        try { sessionStorage.setItem("oud_admin", TOKEN); } catch (err) {}
        $("pw").value = "";
        enter();
      })
      .catch(function () {
        $("gate-btn").disabled = false;
        show("gate-err");
      });
  };

  function enter() {
    hide("gate"); show("panel");
    load();
  }

  function load() {
    fetch(API + "/api/admin/tables?token=" + encodeURIComponent(TOKEN))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) {
          TOKEN = "";
          try { sessionStorage.removeItem("oud_admin"); } catch (e) {}
          hide("panel"); show("gate");
          return;
        }
        HALLS = d.halls;
        ORIGINAL = JSON.parse(JSON.stringify(d.halls));
        tabs();
        select(ACTIVE);
      });
  }

  function tabs() {
    var wrap = $("tabs");
    wrap.innerHTML = "";
    ["outdoor", "main", "narrow"].forEach(function (key) {
      if (!HALLS[key]) { return; }
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = HALL_AR[key] + " (" + HALLS[key].length + ")";
      b.setAttribute("data-hall", key);
      b.onclick = function () { select(key); };
      wrap.appendChild(b);
    });
  }

  function select(key) {
    ACTIVE = key;
    var buttons = $("tabs").querySelectorAll("button");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].classList.toggle("on",
        buttons[i].getAttribute("data-hall") === key);
    }
    $("hall-webp").srcset = "images/hall_" + key + ".webp";
    $("hall-img").src = "images/hall_" + key + ".jpg";
    $("hall-img").alt = HALL_AR[key];
    render();
  }

  /* ----------------------------------------------------- رسم النقاط */
  function render() {
    var box = $("dots");
    box.innerHTML = "";
    HALLS[ACTIVE].forEach(function (t) {
      var el = document.createElement("div");
      el.className = "cal-dot";
      el.textContent = t.number;
      el.style.left = t.x + "%";
      el.style.top = t.y + "%";
      el.title = "طاولة " + t.number + " · سعة " + t.capacity;
      attachDrag(el, t);
      box.appendChild(el);
    });
    readout();
  }

  function attachDrag(el, table) {
    el.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      el.setPointerCapture(e.pointerId);
      el.classList.add("drag");

      function move(ev) {
        var box = $("stage").getBoundingClientRect();
        // النسبة من أبعاد الصورة المعروضة — لا بكسلات مطلقة.
        var x = ((ev.clientX - box.left) / box.width) * 100;
        var y = ((ev.clientY - box.top) / box.height) * 100;
        table.x = Math.round(Math.min(100, Math.max(0, x)) * 10) / 10;
        table.y = Math.round(Math.min(100, Math.max(0, y)) * 10) / 10;
        el.style.left = table.x + "%";
        el.style.top = table.y + "%";
        readout();
      }

      function up(ev) {
        el.classList.remove("drag");
        el.releasePointerCapture(ev.pointerId);
        el.removeEventListener("pointermove", move);
        el.removeEventListener("pointerup", up);
        el.removeEventListener("pointercancel", up);
      }

      el.addEventListener("pointermove", move);
      el.addEventListener("pointerup", up);
      el.addEventListener("pointercancel", up);
    });
  }

  function readout() {
    var moved = 0;
    var lines = HALLS[ACTIVE].map(function (t) {
      var o = ORIGINAL[ACTIVE].filter(function (x) { return x.id === t.id; })[0];
      var changed = o && (o.x !== t.x || o.y !== t.y);
      if (changed) { moved++; }
      return (changed ? "• " : "  ") + t.number + " (" +
        t.x.toFixed(1) + ", " + t.y.toFixed(1) + ")";
    });
    $("readout").textContent = lines.join("\n");
    $("status").textContent = moved ? ("تحرّكت " + moved + " نقطة") : "";
  }

  /* --------------------------------------------------------- الحفظ */
  $("save").onclick = function () {
    var positions = [];
    ["outdoor", "main", "narrow"].forEach(function (key) {
      (HALLS[key] || []).forEach(function (t) {
        positions.push({ id: t.id, x: t.x, y: t.y });
      });
    });
    $("save").disabled = true;
    fetch(API + "/api/admin/tables/positions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: TOKEN, positions: positions })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        $("save").disabled = false;
        if (!d.ok) { return; }
        ORIGINAL = JSON.parse(JSON.stringify(HALLS));
        $("status").innerHTML = '<span class="saved">حُفظت ' +
          d.saved + " طاولة ✅</span>";
        readout();
      })
      .catch(function () { $("save").disabled = false; });
  };

  $("reset").onclick = function () {
    HALLS = JSON.parse(JSON.stringify(ORIGINAL));
    render();
    $("status").textContent = "";
  };

  try {
    var saved = sessionStorage.getItem("oud_admin");
    if (saved) { TOKEN = saved; enter(); }
  } catch (e) { /* التخزين محجوب */ }
})();
