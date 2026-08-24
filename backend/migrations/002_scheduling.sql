-- هجرة 002 — أعمدة تتبّع الجدولة والأدمن (المرحلة 4)
-- السبب: الجدولة تعمل بمسح دوري لقاعدة البيانات لا بمهام في الذاكرة،
-- حتى تنجو من إعادة تشغيل Render. هذه الأعمدة تمنع تكرار الإرسال.
-- آمنة لإعادة التشغيل.

-- طوابع "أُرسل هذا الإجراء" — NULL يعني لم يُرسل بعد.
ALTER TABLE reservations ADD COLUMN IF NOT EXISTS admin_alert2_at    timestamptz;
ALTER TABLE reservations ADD COLUMN IF NOT EXISTS reminder_sent_at   timestamptz;
ALTER TABLE reservations ADD COLUMN IF NOT EXISTS attendance_asked_at timestamptz;

-- رسائل إشعار الأدمن، لتعطيل الأزرار عند أول رد (SPEC 6.3.6).
ALTER TABLE reservations ADD COLUMN IF NOT EXISTS admin_messages jsonb NOT NULL DEFAULT '[]'::jsonb;

-- المسح الدوري يفلتر بالحالة والموعد، فهذا الفهرس يخدمه مباشرة.
CREATE INDEX IF NOT EXISTS idx_res_pending_scan
    ON reservations (status, reservation_at);
