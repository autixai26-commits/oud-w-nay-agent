-- ============================================================
--  عود وناي — مخطط قاعدة البيانات (المرحلة 1)
--  يُنفَّذ مرة واحدة في Supabase ← SQL Editor.
--  آمن لإعادة التشغيل: كل شيء IF NOT EXISTS.
--
--  قاعدة زمنية ملزمة (CONSTRAINTS.md القيد ١):
--  كل الطوابع الزمنية timestamptz أي UTC. التحويل لتوقيت عمّان
--  يتم في الكود عبر to_local()، لا في قاعدة البيانات.
-- ============================================================

-- ------------------------------------------------ 1) الطاولات
-- تحذير (SPEC 5.6): ممنوع إضافة عمود available/booked هنا إطلاقاً.
-- التوفّر يُحسب بالاستعلام عن حجوزات التاريخ المطلوب، وإلا بقيت
-- الطاولات محجوزة للأبد ولم تُصفَّر الخريطة لليوم التالي.
CREATE TABLE IF NOT EXISTS tables (
    id            bigserial PRIMARY KEY,
    table_number  integer NOT NULL UNIQUE,
    hall          text    NOT NULL CHECK (hall IN ('outdoor', 'main', 'narrow')),
    capacity      integer NOT NULL CHECK (capacity > 0),
    pos_x         numeric(5,2) NOT NULL,   -- نسبة مئوية من عرض الصورة
    pos_y         numeric(5,2) NOT NULL,   -- نسبة مئوية من ارتفاع الصورة
    is_active     boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tables_hall ON tables (hall);

-- ------------------------------------------------ 2) الحجوزات
CREATE TABLE IF NOT EXISTS reservations (
    id                bigserial PRIMARY KEY,
    code              text NOT NULL UNIQUE,          -- رمز الحجز المعروض للزبون
    platform          text NOT NULL DEFAULT 'telegram',
    user_id           text NOT NULL,                 -- معرّف الزبون على المنصة
    customer_name     text NOT NULL,
    customer_phone    text NOT NULL,
    party_size        integer NOT NULL CHECK (party_size > 0),
    booking_type      text NOT NULL CHECK (booking_type IN ('family', 'singles')),
    table_id          bigint REFERENCES tables (id), -- NULL للمجموعات الكبيرة (SPEC 5.8)
    -- التاريخ المحلي بعمّان. التوفّر مرتبط بالتاريخ فقط لا بالساعات (SPEC 5.6).
    reservation_date  date NOT NULL,
    reservation_at    timestamptz NOT NULL,          -- الموعد الكامل بـ UTC
    status            text NOT NULL DEFAULT 'pending' CHECK (status IN (
                          'pending', 'confirmed', 'rejected',
                          'seated', 'no_show', 'cancelled', 'completed')),
    is_large_group    boolean NOT NULL DEFAULT false,
    group_type        text,                          -- SPEC 5.8
    occasion          text,                          -- SPEC 5.8
    language          text NOT NULL DEFAULT 'ar' CHECK (language IN ('ar', 'en')),
    decided_by        text,                          -- اسم الأدمن الذي ردّ (SPEC 6.3.6)
    decided_at        timestamptz,
    -- طوابع الجدولة: NULL يعني لم يُرسل بعد. تمنع تكرار الإرسال عند
    -- كل دورة مسح (SPEC 6.3.5 و 6.4).
    admin_alert2_at     timestamptz,
    reminder_sent_at    timestamptz,
    attendance_asked_at timestamptz,
    admin_messages    jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_res_date_status ON reservations (reservation_date, status);
CREATE INDEX IF NOT EXISTS idx_res_table_date  ON reservations (table_id, reservation_date);
CREATE INDEX IF NOT EXISTS idx_res_user        ON reservations (platform, user_id);
CREATE INDEX IF NOT EXISTS idx_res_pending_scan ON reservations (status, reservation_at);

-- طاولة واحدة لا تُحجز مرتين في نفس اليوم بحالة شاغلة (SPEC 5.6 و 6.2).
-- فهرس فريد جزئي: يمنع التعارض على مستوى قاعدة البيانات لا الكود وحده.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_table_per_day
    ON reservations (table_id, reservation_date)
    WHERE status IN ('pending', 'confirmed', 'seated') AND table_id IS NOT NULL;

-- ------------------------------------- 3) جلسات الحجز (روابط الموقع)
-- SPEC 6.1.8: توكن عشوائي، صالح 30 دقيقة، استعمال واحد.
CREATE TABLE IF NOT EXISTS booking_sessions (
    id                bigserial PRIMARY KEY,
    token             text NOT NULL UNIQUE,
    platform          text NOT NULL DEFAULT 'telegram',
    user_id           text NOT NULL,
    booking_type      text NOT NULL CHECK (booking_type IN ('family', 'singles')),
    party_size        integer NOT NULL CHECK (party_size > 0),
    reservation_date  date NOT NULL,
    reservation_at    timestamptz NOT NULL,
    customer_name     text,
    customer_phone    text,
    language          text NOT NULL DEFAULT 'ar' CHECK (language IN ('ar', 'en')),
    expires_at        timestamptz NOT NULL,
    used_at           timestamptz,                   -- NULL = لم يُستعمل بعد
    reservation_id    bigint REFERENCES reservations (id),
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON booking_sessions (expires_at);

-- ------------------------------------------------ 4) الأدمنية
-- SPEC 10.1: يتسجّل الأدمن بنفسه عبر /admin <كلمة السر> لأن البوت
-- لا يستطيع مراسلة أحد برقم الهاتف.
CREATE TABLE IF NOT EXISTS admins (
    id            bigserial PRIMARY KEY,
    platform      text NOT NULL DEFAULT 'telegram',
    user_id       text NOT NULL,
    display_name  text,
    phone         text,
    is_active     boolean NOT NULL DEFAULT true,
    registered_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (platform, user_id)
);

-- ------------------------------------------------ 5) أصناف المنيو
-- SPEC 7.3: ممنوع وجود أي صنف كحولي في هذا الجدول إطلاقاً.
CREATE TABLE IF NOT EXISTS menu_items (
    id           bigserial PRIMARY KEY,
    name_ar      text NOT NULL,
    name_en      text NOT NULL,
    price        numeric(7,3) NOT NULL CHECK (price >= 0),  -- دينار بثلاث خانات
    category     text NOT NULL,
    category_ar  text NOT NULL,
    category_en  text NOT NULL,
    -- التصنيف الفرعي: يقسّم الفئات الكبيرة لصفحات أزرار (SPEC 7.1، حد 10 خيارات).
    subcategory     text NOT NULL,
    subcategory_ar  text NOT NULL,
    subcategory_en  text NOT NULL,
    menu_group   text NOT NULL CHECK (menu_group IN ('food', 'drinks', 'shisha')),
    note_en      text,
    sort_order   integer NOT NULL DEFAULT 0,
    is_active    boolean NOT NULL DEFAULT true,
    UNIQUE (name_ar)
);
CREATE INDEX IF NOT EXISTS idx_menu_category ON menu_items (menu_group, category, subcategory, sort_order);

-- ------------------------------------------- 6) حالة محادثة المستخدم
-- SPEC 11: المفتاح (platform, user_id) وليس telegram_id وحده،
-- حتى تعمل نفس الجداول مع واتساب لاحقاً بلا هجرة.
CREATE TABLE IF NOT EXISTS user_state (
    id          bigserial PRIMARY KEY,
    platform    text NOT NULL DEFAULT 'telegram',
    user_id     text NOT NULL,
    language    text CHECK (language IN ('ar', 'en')),
    state       text,
    data        jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (platform, user_id)
);

-- ------------------------------------------------ 7) الإعدادات
CREATE TABLE IF NOT EXISTS settings (
    key         text PRIMARY KEY,
    value       jsonb NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- ------------------------------------------------ الحماية
-- الباك إند يتصل بمفتاح service_role وهو يتجاوز RLS.
-- تفعيل RLS بلا أي policy يعني: المفتاح العام anon لا يقرأ ولا يكتب شيئاً.
ALTER TABLE tables           ENABLE ROW LEVEL SECURITY;
ALTER TABLE reservations     ENABLE ROW LEVEL SECURITY;
ALTER TABLE booking_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE admins           ENABLE ROW LEVEL SECURITY;
ALTER TABLE menu_items       ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_state       ENABLE ROW LEVEL SECURITY;
ALTER TABLE settings         ENABLE ROW LEVEL SECURITY;
