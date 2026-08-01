// Ссылка на карточку сделки в Битриксе.
export const BITRIX_DEAL_URL = (id) => `https://simb-ad.bitrix24.ru/crm/deal/details/${id}/`

// Цвет слоя денег по имени (ключ r.money_layer в реестре/дашборде). Единый
// «классический» набор токенов; аналитика использует свой визуальный язык.
export const LAYER_COLOR = {
  'планируемые': 'var(--muted)',
  'реализуемые': 'var(--accent)',
  'фактические': 'var(--success)',
  'Без группы': 'var(--danger)',
}
