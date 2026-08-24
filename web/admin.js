/* لوحة عرض الحجوزات — SPEC 10.3. عرض فقط، بلا أي تعديل. */
(function () {
  "use strict";

  var API = (window.OUD_CONFIG && window.OUD_CONFIG.apiBase) || "";
  var q = new URLSearchParams(location.search);
  if (q.get("api")) { API = q.get("api"); }

  var TOKEN = "";
  var DAY = "";
  var STATUS = "";
  var timer = null;

  var STATUS_AR = {
    pending: "بانتظار التثبيت", confirmed: "مثبّت", seated: "على الطاولة",
    completed: "منتهي", no_show: "ما حضر", cancelled: "ملغى",
    rejected: "مرفوض"
  };
  var HALL_AR = { outdoor: "الخارجية", main: "الكبيرة", narrow: "الضيقة" };
  var KIND_AR = { family: "عائلة", singles: "شباب" };

  function $(id) { return document.getElementById(id); }
  function show(id) { $(id).classList.remove("hidden"); }
  function hide(id) { $(id).classList.add("hidden"); }

  function isoDay(offset) {
    var d = new Date();
    d.setDate(d.getDate() + (offset || 0));
    // نبني التاريخ محلياً لا بـ toISOString لأنها تحوّل إلى UTC
    // فتُرجع اليوم السابق في ساعات المساء بتوقيت عمّان.
    var m = String(d.getMonth() + 1).padStart(2, "0");
    var day = String(d.getDate()).padStart(2, "0");
    return d.getFullYear() + "-" + m + "-" + day;
  }

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
        // التوكن موقّع وله صلاحية، فحفظه يوفّر إعادة الدخول كل تحديث.
        try { sessionStorage.setItem("oud_admin", TOKEN); } catch (err) {}
        $("pw").value = "";
        enter();
      })
      .catch(function () {
        $("gate-btn").disabled = false;
        show("gate-err");
      });
  };

  $("logout").onclick = function () {
    TOKEN = "";
    try { sessionStorage.removeItem("oud_admin"); } catch (e) {}
    if (timer) { clearInterval(timer); }
    hide("panel"); show("gate");
  };

  function enter() {
    hide("gate"); show("panel");
    DAY = isoDay(0);
    $("date-pick").value = DAY;
    load();
    // SPEC 10.3 — تحديث تلقائي كل 30 ثانية.
    if (timer) { clearInterval(timer); }
    timer = setInterval(load, 30000);
  }

  /* --------------------------------------------------------- الفلاتر */
  var chips = document.querySelectorAll("#day-chips .chip[data-day]");
  for (var i = 0; i < chips.length; i++) {
    chips[i].onclick = function () {
      for (var j = 0; j < chips.length; j++) { chips[j].classList.remove("on"); }
      this.classList.add("on");
      DAY = isoDay(this.getAttribute("data-day") === "tomorrow" ? 1 : 0);
      $("date-pick").value = DAY;
      load();
    };
  }

  $("date-pick").onchange = function () {
    if (!this.value) { return; }
    for (var j = 0; j < chips.length; j++) { chips[j].classList.remove("on"); }
    DAY = this.value;
    load();
  };

  $("status-filter").onchange = function () {
    STATUS = this.value;
    load();
  };

  /* --------------------------------------------------------- التحميل */
  function load() {
    if (!TOKEN) { return; }
    var url = API + "/api/admin/reservations?token=" +
      encodeURIComponent(TOKEN) + "&date=" + encodeURIComponent(DAY) +
      (STATUS ? "&status=" + encodeURIComponent(STATUS) : "");
    fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) {
          if (d.reason === "unauthorized") { return $("logout").onclick(); }
          return;
        }
        render(d);
      })
      .catch(function () { /* الشبكة تتعافى في الدورة التالية */ });
  }

  function render(d) {
    $("head-date").textContent = d.date;
    $("stats").innerHTML = "";
    [["الحجوزات", d.stats.count], ["طاولات مشغولة", d.stats.busy + " / " + d.stats.total],
     ["نسبة الإشغال", d.stats.rate + "%"], ["مقاعد محجوزة", d.stats.seats]
    ].forEach(function (s) {
      var el = document.createElement("div");
      el.className = "stat";
      var b = document.createElement("b");
      b.textContent = s[1];
      var sp = document.createElement("span");
      sp.textContent = s[0];
      el.appendChild(b); el.appendChild(sp);
      $("stats").appendChild(el);
    });

    var body = $("rows");
    body.innerHTML = "";
    d.rows.forEach(function (r) {
      var tr = document.createElement("tr");
      if (r.large_group) { tr.className = "large"; }
      var cells = [
        [r.code, "code"], [r.time, ""],
        [r.table === null ? "—" : String(r.table), ""],
        [r.hall ? HALL_AR[r.hall] : "—", ""],
        [String(r.people), ""], [KIND_AR[r.kind] || r.kind, ""],
        [r.name, ""], [r.phone, ""]
      ];
      cells.forEach(function (c) {
        var td = document.createElement("td");
        td.textContent = c[0];
        if (c[1]) { td.className = c[1]; }
        tr.appendChild(td);
      });
      var td = document.createElement("td");
      var pill = document.createElement("span");
      pill.className = "pill s-" + r.status;
      pill.textContent = STATUS_AR[r.status] || r.status;
      td.appendChild(pill);
      tr.appendChild(td);
      body.appendChild(tr);
    });

    $("empty").classList.toggle("hidden", d.rows.length > 0);
    var now = new Date();
    $("refreshed").textContent = "آخر تحديث " +
      String(now.getHours()).padStart(2, "0") + ":" +
      String(now.getMinutes()).padStart(2, "0") + " · يتحدّث كل 30 ثانية";
  }

  /* جلسة محفوظة من تحديث سابق للصفحة */
  try {
    var saved = sessionStorage.getItem("oud_admin");
    if (saved) { TOKEN = saved; enter(); }
  } catch (e) { /* التخزين محجوب — يدخل بكلمة السر عادي */ }
})();
