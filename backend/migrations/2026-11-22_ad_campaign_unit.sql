-- Единица объёма РК: show | click (22.11.2026). Ставится из calc_form услуги сделки (CPC → click).
ALTER TABLE ad_campaign ADD COLUMN IF NOT EXISTS unit varchar(8) NOT NULL DEFAULT 'show'
    CHECK (unit IN ('show', 'click'));
