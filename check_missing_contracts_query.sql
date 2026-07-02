SELECT
    cp.name                            AS kontragent,
    cp.inn                             AS inn,
    COUNT(o.id)                        AS kol_operatsiy,
    TO_CHAR(MAX(o.date), 'DD.MM.YYYY') AS poslednyaya_operatsiya,
    ROUND(SUM(o.income)::numeric, 2)   AS prikhod,
    ROUND(SUM(o.expense)::numeric, 2)  AS raskhod
FROM operations o
JOIN counterparties cp ON cp.id = o.counterparty_id
WHERE o.date >= '2025-01-01'
  AND o.counterparty_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM contracts c
      WHERE c.counterparty_id = cp.id
  )
GROUP BY cp.id, cp.name, cp.inn
ORDER BY (SUM(o.income) + SUM(o.expense)) DESC NULLS LAST;
