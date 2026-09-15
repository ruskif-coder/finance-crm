import { downloadName } from './salesFormat'
import { downloadFile } from './download'

// ── Скачивание НАШЕГО медиаплана: ОДНА точка на все экраны ───────────────────
//
// До 13.09.2026 имя файла собиралось в ЧЕТЫРЁХ местах двумя разными способами:
// конструктор и реестр медиапланов звали downloadName и получали
// «MP Simb-AD <Название РК> 13.09.2026 20-14.pdf», а карточка сделки и расхлоп строки
// в реестре сделок подставляли техническое «MP_12_v3.pdf». Один и тот же документ
// приезжал человеку под двумя именами в зависимости от того, с какого экрана он нажал.
//
// Имя собирается на фронте, а не на сервере, потому что в нём есть отметка времени
// СКАЧИВАНИЯ: два экспорта одного плана подряд не должны затирать друг друга в папке
// «Загрузки». Серверное имя осталось запасным — его видно, только если открыть ручку
// напрямую, минуя интерфейс.

export const MP_PREFIX = 'MP Simb-AD'

// plan — любой объект плана: и «шапка» из deal.our_mps, и полные данные из
// /sales/media-plans/{id} несут title. Без названия downloadName подставит «Медиаплан».
export const mpFileName = (plan, ext) => downloadName(plan?.title, ext, MP_PREFIX)

export const mpFileUrl = (plan, ext) => (ext === 'xlsx'
  ? `/sales/media-plans/${plan.id}/export.xlsx`
  : `/sales/media-plans/${plan.id}/pdf`)

// Возвращает true/false — экран снимает свой индикатор занятости.
export const downloadMp = (plan, ext) => downloadFile(mpFileUrl(plan, ext), mpFileName(plan, ext))
