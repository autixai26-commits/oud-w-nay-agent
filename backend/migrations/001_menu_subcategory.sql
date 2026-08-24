-- هجرة 001 — إضافة التصنيف الفرعي لأصناف المنيو
-- السبب: SPEC 7.1 يحدّ كل مستوى أزرار بـ10 خيارات، وفئتا المقبلات
-- الباردة (34 صنف) والساخنة (27) تتجاوزانه. القسمة قرار المالك.
-- آمن لإعادة التشغيل.

ALTER TABLE menu_items ADD COLUMN IF NOT EXISTS subcategory     text;
ALTER TABLE menu_items ADD COLUMN IF NOT EXISTS subcategory_ar  text;
ALTER TABLE menu_items ADD COLUMN IF NOT EXISTS subcategory_en  text;

DROP INDEX IF EXISTS idx_menu_category;
CREATE INDEX IF NOT EXISTS idx_menu_category
    ON menu_items (menu_group, category, subcategory, sort_order);
