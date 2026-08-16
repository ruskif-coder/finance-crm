// Чистая логика разбора правил редиректов — без зависимостей от браузера и от Next,
// чтобы её можно было импортировать и из клиентского кода (lib/nav.js), и из проверки
// на голом node (scripts/check-nav.mjs). Копия этой логики в двух местах и была бы тем
// самым багом, который проверка ловит, поэтому источник ровно один — этот файл.
//
// Синтаксис from — как у Next: ":id" и ":id(<своя regex>)". Порядок правил значим:
// "/deals/mp/:id" обязано стоять после "/deals/mp/pdf/:id", иначе съест его.

export const compileRule = (r) => {
  const names = []
  let src = ''
  let i = 0
  while (i < r.from.length) {
    const ch = r.from[i]
    if (ch === ':') {
      let j = i + 1
      while (j < r.from.length && /[A-Za-z0-9_]/.test(r.from[j])) j++
      names.push(r.from.slice(i + 1, j))
      let body = '[^/]+'
      if (r.from[j] === '(') {
        // ищем парную закрывающую скобку с учётом вложенности
        let depth = 0, k = j
        for (; k < r.from.length; k++) {
          if (r.from[k] === '(') depth++
          else if (r.from[k] === ')' && --depth === 0) break
        }
        body = r.from.slice(j + 1, k)
        j = k + 1
      }
      src += '(' + body + ')'
      i = j
    } else {
      src += ch.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      i++
    }
  }
  return { re: new RegExp('^' + src + '$'), names, to: r.to }
}

export const compileRules = (redirects) => (redirects || []).map(compileRule)

// Клиентский двойник серверных редиректов. Второй аргумент — список правил
// (сырых из карты либо уже скомпилированных): так модуль остаётся чистым.
export const resolveLegacy = (href, redirects) => {
  if (typeof href !== 'string' || !href) return href
  const rules = (redirects || []).map(r => (r && r.re ? r : compileRule(r)))
  // query и хеш не участвуют в сопоставлении, но переносятся на новый адрес
  const m = href.match(/^([^?#]*)(.*)$/)
  const path = m[1]
  const tail = m[2] || ''
  for (const rule of rules) {
    const hit = path.match(rule.re)
    if (!hit) continue
    let out = rule.to
    rule.names.forEach((n, idx) => {
      out = out.split(':' + n).join(hit[idx + 1])
    })
    return out + tail
  }
  return href
}
