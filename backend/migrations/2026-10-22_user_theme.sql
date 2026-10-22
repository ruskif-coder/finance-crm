-- Тема интерфейса пользователя (владелец 22.10.2026: «да, давай поле»): День · Ночь · Графит ходят за человеком
-- на любое устройство, а не живут в одном браузере. Пусто — светлая. Пишет сам пользователь (PUT /api/auth/me/theme).
-- Повтор безопасен.
ALTER TABLE users ADD COLUMN IF NOT EXISTS theme varchar(12)
    CONSTRAINT ck_users_theme CHECK (theme IN ('light', 'dark', 'graphite'));
