-- Темы NAVY (хендофф docs/navy_theme.zip, владелец 17.11.2026: «добавить Navy день и Navy ночь» рядом с прежними пятью).
-- Тема — личная настройка пользователя; проверка допускает два новых названия. Повторный запуск безопасен.
ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_theme;
ALTER TABLE users ADD CONSTRAINT ck_users_theme
  CHECK (theme IN ('light', 'dark', 'graphite', 'pink', 'japandi', 'navy', 'navy-dark'));
