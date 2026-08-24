/* عود وناي — منطق صفحة اختيار الطاولة (SPEC 6.2).
   جافاسكربت خام بلا أي مكتبة وبلا build step. */
(function () {
  "use strict";

  var API = (window.OUD_CONFIG && window.OUD_CONFIG.apiBase) || "";
  var params = new URLSearchParams(location.search);
  var TOKEN = params.get("t") || "";
  // مسار الباك إند يمكن تجاوزه بـ ?api= أثناء التطوير المحلي فقط.
  if (params.get("api")) { API = params.get("api"); }

  var LANG = "ar";
  var HALLS = null;
  var BOOKING = null;
  var ACTIVE = null;
  var CHOSEN = null;

  var T = {
    ar: {
      halls: { outdoor: "الصالة الخارجية", main: "الصالة الكبيرة", narrow: "الصالة الضيقة" },
      seats: function (n) { return n + " مقاعد"; },
      table: function (n) { return "طاولة " + n; },
      available: "Available — متاحة",
      booked: "Booked — محجوزة",
      tooSmall: "سعتها أقل من عدد الأشخاص",
      lockedHall: "هذه الصالة للعائلات فقط",
      hint: "اضغط على نقطة خضراء لاختيار طاولتك",
      confirm: "تأكيد الحجز",
      rowDate: "التاريخ", rowTime: "الوقت", rowPeople: "عدد الأشخاص",
      rowHall: "الصالة", rowTable: "الطاولة", rowName: "الاسم",
      ok: "تأكيد", cancel: "رجوع",
      doneTitle: "تم اختيار طاولتك",
      doneBody: "رجاءً ارجع للبوت — بانتظار تثبيت الحجز.",
      doneCode: "رمز الحجز: ",
      errTaken: "للأسف حجزها حدا قبلك بثواني. اختر طاولة ثانية.",
      errGeneric: "صار خلل، جرّب كمان مرة.",
      invalid: {
        expired: ["انتهت صلاحية الرابط", "الرابط صالح 30 دقيقة فقط. ارجع للبوت واطلب رابط جديد."],
        used: ["الرابط مستعمَل", "هذا الرابط استُخدم مرة واحدة. ارجع للبوت لو بدك تحجز من جديد."],
        not_found: ["رابط غير صحيح", "تأكد من فتح الرابط كما وصلك من البوت."],
        no_token: ["رابط ناقص", "افتح الرابط كما وصلك من البوت."]
      }
    },
    en: {
      halls: { outdoor: "Outdoor hall", main: "Main hall", narrow: "Narrow hall" },
      seats: function (n) { return n + " seats"; },
      table: function (n) { return "Table " + n; },
      available: "Available — متاحة",
      booked: "Booked — محجوزة",
      tooSmall: "Capacity is smaller than your party",
      lockedHall: "This hall is for families only",
      hint: "Tap a green dot to pick your table",
      confirm: "Confirm your booking",
      rowDate: "Date", rowTime: "Time", rowPeople: "People",
      rowHall: "Hall", rowTable: "Table", rowName: "Name",
      ok: "Confirm", cancel: "Back",
      doneTitle: "Your table is selected",
      doneBody: "Please return to the bot — waiting for confirmation.",
      doneCode: "Booking code: ",
      errTaken: "Sorry, someone booked it seconds ago. Please pick another table.",
      errGeneric: "Something went wrong, please try again.",
      invalid: {
        expired: ["This link has expired", "Links are valid for 30 minutes. Go back to the bot for a new one."],
        used: ["Link already used", "This link works once. Return to the bot to book again."],
        not_found: ["Invalid link", "Please open the link exactly as the bot sent it."],
        no_token: ["Missing link", "Please open the link as the bot sent it."]
      }
    }
  };

  function t() { return T[LANG]; }
  function $(id) { return document.getElementById(id); }
  function show(id) { $(id).classList.remove("hidden"); }
  function hide(id) { $(id).classList.add("hidden"); }

  function applyLang() {
    document.documentElement.lang = LANG;
    document.documentElement.dir = LANG === "ar" ? "rtl" : "ltr";
    var nodes = document.querySelectorAll("[data-ar]");
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].textContent = nodes[i].getAttribute("data-" + LANG);
    }
  }

  function fail(reason) {
    var msg = t().invalid[reason] || t().invalid.not_found;
    $("invalid-title").textContent = msg[0];
    $("invalid-body").textContent = msg[1];
    hide("loading"); hide("picker"); show("invalid");
  }

  /* ------------------------------------------------------- التحميل */
  function load() {
    if (!TOKEN) { applyLang(); return fail("no_token"); }
    fetch(API + "/api/booking/" + encodeURIComponent(TOKEN))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.state !== "ok") {
          LANG = "ar"; applyLang(); return fail(d.state);
        }
        BOOKING = d.booking;
        HALLS = d.halls;
        LANG = BOOKING.language === "en" ? "en" : "ar";
        applyLang();
        header();
        tabs();
        // نفتح أول صالة غير مقفولة حتى لا يرى الزبون شاشة مقفلة أولاً.
        var first = ["outdoor", "main", "narrow"].filter(function (h) {
          return HALLS[h] && !HALLS[h].locked;
        })[0] || "outdoor";
        select(first);
        hide("loading"); show("picker");
      })
      .catch(function () { applyLang(); fail("not_found"); });
  }

  function header() {
    $("summary").textContent = [
      BOOKING.weekday + " " + BOOKING.date,
      BOOKING.time,
      BOOKING.party_size + (LANG === "ar" ? " أشخاص" : " people")
    ].join(" · ");
    $("hint").textContent = t().hint;
  }

  /* ------------------------------------------------------ التبويبات */
  function tabs() {
    var wrap = $("tabs");
    wrap.innerHTML = "";
    ["outdoor", "main", "narrow"].forEach(function (key) {
      var hall = HALLS[key];
      if (!hall) { return; }
      var free = hall.tables.filter(function (x) { return x.selectable; }).length;
      var b = document.createElement("button");
      b.type = "button";
      b.innerHTML = t().halls[key] +
        (hall.locked ? " 🔒" : ' <span class="pad">(' + free + ")</span>");
      b.onclick = function () { select(key); };
      b.setAttribute("data-hall", key);
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
    // WebP أساسي وJPG احتياطي — CONSTRAINTS القيد ٣.
    $("hall-webp").srcset = "images/hall_" + key + ".webp";
    $("hall-img").src = "images/hall_" + key + ".jpg";
    $("hall-img").alt = t().halls[key];
    render();
  }

  /* --------------------------------------------------------- النقاط */
  function render() {
    var hall = HALLS[ACTIVE];
    var box = $("dots");
    box.innerHTML = "";

    if (hall.locked) {
      $("lock-text").textContent = t().lockedHall;
      show("hall-lock");
    } else {
      hide("hall-lock");
    }

    hall.tables.forEach(function (tb) {
      var el = document.createElement(tb.selectable ? "button" : "div");
      el.className = "dot d-" + (tb.state === "too_small" ? "small" : tb.state);
      /* الإحداثيات مئوية من الحافة اليسرى كما في SPEC القسم 4، فنستخدم left
         حتى في صفحة RTL — استعمال right هنا يعكس الخريطة أفقياً. */
      el.style.left = tb.x + "%";
      el.style.top = tb.y + "%";
      el.textContent = tb.number;
      if (tb.selectable) {
        el.type = "button";
        el.onclick = function () { openModal(tb); };
      } else {
        el.setAttribute("aria-disabled", "true");
      }
      el.onmouseenter = function () { tip(tb, el); };
      el.onmouseleave = clearTip;
      box.appendChild(el);
    });
  }

  function tip(tb, el) {
    clearTip();
    var label = tb.state === "available" ? t().available
      : tb.state === "booked" ? t().booked : t().tooSmall;
    var d = document.createElement("div");
    d.className = "tip";
    d.id = "tip";
    d.textContent = t().table(tb.number) + " · " + label + " · " + t().seats(tb.capacity);
    d.style.left = tb.x + "%";
    d.style.top = (tb.y > 12 ? tb.y - 7 : tb.y + 7) + "%";
    $("dots").appendChild(d);
  }

  function clearTip() {
    var old = $("tip");
    if (old) { old.remove(); }
  }

  /* ------------------------------------------------- نافذة التأكيد */
  function openModal(tb) {
    CHOSEN = tb;
    $("m-title").textContent = t().confirm;
    var rows = [
      [t().rowDate, BOOKING.weekday + " " + BOOKING.date],
      [t().rowTime, BOOKING.time],
      [t().rowPeople, String(BOOKING.party_size)],
      [t().rowHall, t().halls[ACTIVE]],
      [t().rowTable, String(tb.number) + " (" + t().seats(tb.capacity) + ")"],
      [t().rowName, BOOKING.name]
    ];
    $("m-rows").innerHTML = rows.map(function (r) {
      return "<dt></dt><dd></dd>";
    }).join("");
    var dts = $("m-rows").querySelectorAll("dt");
    var dds = $("m-rows").querySelectorAll("dd");
    rows.forEach(function (r, i) {
      dts[i].textContent = r[0];
      dds[i].textContent = r[1];
    });
    $("m-ok").textContent = t().ok;
    $("m-cancel").textContent = t().cancel;
    $("m-ok").disabled = false;
    hide("m-err");
    show("modal");
  }

  $("m-cancel").onclick = function () { hide("modal"); };

  $("m-ok").onclick = function () {
    $("m-ok").disabled = true;
    fetch(API + "/api/booking/" + encodeURIComponent(TOKEN) + "/reserve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ table_id: CHOSEN.id })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.ok) { return done(d.code); }
        if (d.reason === "expired" || d.reason === "used" ||
            d.reason === "not_found") {
          hide("modal");
          return fail(d.reason);
        }
        $("m-err").textContent =
          d.reason === "taken" ? t().errTaken : t().errGeneric;
        show("m-err");
        $("m-ok").disabled = false;
      })
      .catch(function () {
        $("m-err").textContent = t().errGeneric;
        show("m-err");
        $("m-ok").disabled = false;
      });
  };

  function done(code) {
    $("done-title").textContent = t().doneTitle;
    $("done-body").textContent = t().doneBody;
    $("done-code").textContent = t().doneCode + code;
    hide("modal"); hide("picker"); show("done");
  }

  load();
})();
