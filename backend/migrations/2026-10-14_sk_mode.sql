-- СК (агентская комиссия): способ выплаты и процент (владелец 14.10.2026; схема утверждена).
-- У юрлица — способ (постоплата / скидка в счёт) и базовый %; на закрытии сделки — свои значения, подставленные от плательщика
-- и поправленные аккаунтом. Без способа СК не закрыть Альфарм-Таргет. Повторно накатываемая, ничего не удаляет.
ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS sk_mode VARCHAR(16)
    CHECK (sk_mode IS NULL OR sk_mode IN ('постоплата', 'скидка в счёт'));
ALTER TABLE counterparties ADD COLUMN IF NOT EXISTS sk_percent DOUBLE PRECISION
    CHECK (sk_percent IS NULL OR (sk_percent >= 0 AND sk_percent <= 100));
COMMENT ON COLUMN counterparties.sk_mode IS 'Способ СК юрлица: постоплата (счёт на полную, СК выплачиваем потом) или скидка в счёт. Пусто — не задано';
COMMENT ON COLUMN counterparties.sk_percent IS 'Базовый % СК юрлица; на закрытии сделки правится (final_recon_deals.sk_percent). Пусто — СК нет';

-- Данные закрытия сделки (пакет app/final_recon, спринт 4). Строка появляется, когда аккаунт правит закрытие; до того значения берутся от плательщика.
CREATE TABLE IF NOT EXISTS final_recon_deals (
    deal_id     INTEGER     PRIMARY KEY REFERENCES sales_deals (id),
    -- Способ и % СК этой сделки: зафиксированы на закрытии, смена настроек юрлица их не двигает.
    sk_mode     VARCHAR(16) CHECK (sk_mode IS NULL OR sk_mode IN ('постоплата', 'скидка в счёт')),
    sk_percent  DOUBLE PRECISION CHECK (sk_percent IS NULL OR (sk_percent >= 0 AND sk_percent <= 100)),
    updated_by  INTEGER     REFERENCES users (id),
    updated_at  TIMESTAMP   NOT NULL DEFAULT now()
);
COMMENT ON TABLE final_recon_deals IS 'Данные закрытия сделки (итоговая сверка): СК — способ и %, поправленные аккаунтом.';
