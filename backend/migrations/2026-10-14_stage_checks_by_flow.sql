-- Требования стадий — по ЦИКЛУ, а не по услуге еФарм (владелец 14.10.2026). До этого 33 из 34 требований были привязаны к service_id 28,
-- и у остальных услуг на стадиях не было проверок вовсе, в том числе документных.
--   полный цикл — работа трафика и DSP: креативы, площадки, ЕРИД, РК, «РК завершена», факт; ОРД (изначальный договор, акты) — до решения 15.10;
--   оба цикла  — сделка и документы: воронка, плательщик, доходный договор, МП, ДС, подписант, счёт, УПД, отчёт, ЭДО, оплата;
--   контур аккаунта — «сделка завершена аккаунтом» вместо «РК завершена» на стадиях ДО.
-- Повторно накатываемая: условия выставляются по ключу проверки, а не добавляются.
UPDATE sales_stage_checks SET applies_when = '{"closing_flow": "полный цикл"}'::jsonb
 WHERE applies_when = '{"service_id": 28}'::jsonb
   AND check_key IN ('one_pair_ready', 'creatives_accepted', 'placements_approved', 'erid_issued', 'campaign_ready',
                     'campaign_finished', 'fact_collected', 'ord_initial_contract', 'ord_acts_sent');
UPDATE sales_stage_checks SET applies_when = NULL
 WHERE applies_when = '{"service_id": 28}'::jsonb
   AND check_key IN ('realization_pipeline', 'payer_set', 'final_contract', 'mp_linked', 'annex_generated', 'signatory_filled',
                     'ds_signed', 'invoice_issued', 'upd_issued', 'report_attached', 'edo_sent', 'payment_received');

-- Дубль «доходный договор (контур аккаунта)» заменён общим требованием.
DELETE FROM sales_stage_checks WHERE check_key = 'final_contract_account';

-- Контур аккаунта: «сделка завершена аккаунтом» — там же и с той же блокировкой, что «РК завершена».
INSERT INTO sales_stage_checks (stage_id, check_key, is_blocking, applies_when, sort_order, hint)
SELECT c.stage_id, 'account_finished', c.is_blocking, '{"closing_flow": "контур аккаунта"}'::jsonb, c.sort_order, NULL
  FROM sales_stage_checks c WHERE c.check_key = 'campaign_finished'
ON CONFLICT (stage_id, check_key) DO NOTHING;

-- На самой «Итоговой сверке» «завершено аккаунтом» не ставится: вход в неё И ЕСТЬ завершение (кнопка «Завершить»), иначе круг.
DELETE FROM sales_stage_checks c USING sales_stages st
 WHERE st.id = c.stage_id AND st.name = 'Итоговая сверка' AND c.check_key = 'account_finished';
