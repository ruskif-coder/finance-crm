-- Пять тем вместо трёх (владелец 22.10.2026, хендофф docs/темки.zip: + «Розовая», «Джапанди»).
-- Ограничение пересоздаётся со списком из пяти; само поле users.theme не трогаем. Повтор безопасен.
ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_theme;
ALTER TABLE users ADD CONSTRAINT ck_users_theme CHECK (theme IN ('light', 'dark', 'graphite', 'pink', 'japandi'));
