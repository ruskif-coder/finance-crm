-- «Условия работы»: бонусы для аккаунта (владелец 27.10.2026) — креативы и отчёты делаем бонусом, и при каком условии.
-- Флажок и комментарий парой: комментарий без флажка не хранится (его стирает save_work). Повторно накатываемая.
ALTER TABLE sk_work_terms ADD COLUMN IF NOT EXISTS creatives_bonus      boolean NOT NULL DEFAULT false;  -- креативы делаем бонусом
ALTER TABLE sk_work_terms ADD COLUMN IF NOT EXISTS creatives_bonus_note text;                            -- при каком условии
ALTER TABLE sk_work_terms ADD COLUMN IF NOT EXISTS reports_bonus        boolean NOT NULL DEFAULT false;  -- отчёты делаем бонусом
ALTER TABLE sk_work_terms ADD COLUMN IF NOT EXISTS reports_bonus_note   text;                            -- при каком условии
