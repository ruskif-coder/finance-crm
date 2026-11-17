-- Навигация v3 (хендофф design_handoff_nav_mix, 17.11.2026): закреплённые экраны и недавние — у пользователя, а не в
-- браузере (владелец 17.11.2026). Строки нет — действуют значения по умолчанию (закреплены «Операции»), поэтому
-- бэкфилл не нужен. Повторный накат безопасен.
CREATE TABLE IF NOT EXISTS user_nav_prefs (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    -- адреса закреплённых экранов в порядке закрепления, не больше трёх
    pinned     JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- адреса последних открытых экранов, свежий первым, не больше двенадцати
    recent     JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);
