/**
 * Печатная форма приложения к договору.
 *
 * Одна страница на оба формата вывода: её печатает сайдкар headless-Chromium в нативный
 * PDF (тем же способом, что медиаплан), и её же человек видит в предпросмотре. Второй
 * вёрстки документа в проекте нет — расходиться нечему.
 *
 * Данные приходят двумя путями. В режиме сайдкара бэкенд инжектит их в `window.__ANNEX__`
 * ещё до скриптов страницы: браузеру не нужен ни токен, ни доступ к API, потому что
 * доступ уже проверил бэкенд, который единственный ходит в сайдкар. В обычном режиме
 * страница тянет их сама по id.
 *
 * Вёрстка — A4 с типографикой договора: Times, 12 пт, чёрным по белому. Тёмной темы тут
 * нет и быть не может: документ печатают на бумаге.
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import api, { auth } from '@/lib/api'
import AnnexDocument from '@/components/annex/AnnexDocument'

export default function AnnexPrint() {
  const router = useRouter()
  const { id } = router.query
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (window.__ANNEX__) { setD(window.__ANNEX__); return }
    if (!id) return
    api.get(`/annexes/${id}`, auth())
      .then(r => setD(r.data.doc ? { ...r.data.doc, rows: r.data.rows || [] } : r.data))
      .catch(e => setErr(e?.response?.data?.detail || 'Не удалось загрузить приложение'))
  }, [id])

  // Флаг для сайдкара: он ждёт его, прежде чем печатать, — иначе в PDF уедет пустая
  // страница, пока данные ещё грузятся.
  useEffect(() => { if (d && typeof window !== 'undefined') window.__ANNEX_RENDERED__ = true }, [d])

  if (err) return <div style={{ padding: 40, fontFamily: 'Times New Roman, serif' }}>{err}</div>
  if (!d) return <div style={{ padding: 40, fontFamily: 'Times New Roman, serif' }}>Загрузка…</div>

  return (
    <>
      <Head><title>{d.number || d.words?.nom || 'Приложение'}</title></Head>
      <style>{`
        /* Альбомная ориентация: в документе таблица медиаплана из тринадцати колонок, и в портретной A4 она сжимается до
           нечитаемого. Сайдкар печатает с preferCSSPageSize, поэтому размер страницы задаётся здесь, а не в его коде.
           Код мастер-сделки на каждом листе печатает сервис PDF колонтитулом принтера (поле footer, 21.10.2026). */
        @page { size: A4 landscape; margin: 15mm 16mm; }
        html, body { background: #fff; }
      `}</style>
      <AnnexDocument d={d} />
    </>
  )
}
