(() => {
  'use strict'

  const loader = document.currentScript
  const API = loader?.dataset.api || '/api/v1/plugin/MediaRatings/detail'
  const ROOT_ID = 'moviepilot-multi-source-ratings'
  let requestSerial = 0
  let lastKey = ''

  const sourceClass = id => `mpr-source-${String(id || '').replace(/[^a-z0-9_-]/gi, '')}`
  const voteLabel = votes => {
    if (votes === null || votes === undefined) return ''
    return `${new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 1 }).format(votes)} 人`
  }

  function installStyle() {
    if (document.getElementById('moviepilot-ratings-style')) return
    const style = document.createElement('style')
    style.id = 'moviepilot-ratings-style'
    style.textContent = `
      #${ROOT_ID}{margin:1rem 0 .25rem;grid-column:1/-1}
      #${ROOT_ID} .mpr-heading{display:flex;align-items:center;gap:.5rem;margin:0 0 .7rem;font-size:1rem;font-weight:650;color:rgba(255,255,255,.9)}
      #${ROOT_ID} .mpr-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:.65rem}
      #${ROOT_ID} .mpr-card{position:relative;display:flex;align-items:center;gap:.7rem;min-height:66px;padding:.75rem .85rem;border:1px solid rgba(255,255,255,.13);border-radius:13px;background:rgba(22,25,31,.62);backdrop-filter:blur(12px);color:inherit;text-decoration:none;transition:transform .16s ease,border-color .16s ease,background .16s ease}
      #${ROOT_ID} .mpr-card:hover{transform:translateY(-2px);border-color:rgba(255,255,255,.28);background:rgba(35,39,48,.82)}
      #${ROOT_ID} .mpr-score{display:grid;place-items:center;flex:0 0 43px;height:43px;border-radius:50%;background:conic-gradient(#8b5cf6 calc(var(--score)*10%),rgba(255,255,255,.12) 0);font-size:.92rem;font-weight:750;color:#fff}
      #${ROOT_ID} .mpr-score:before{content:'';position:absolute;width:35px;height:35px;border-radius:50%;background:#20242c}
      #${ROOT_ID} .mpr-score span{position:relative;z-index:1}
      #${ROOT_ID} .mpr-meta{min-width:0;display:flex;flex-direction:column}
      #${ROOT_ID} .mpr-name{font-size:.83rem;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      #${ROOT_ID} .mpr-votes{margin-top:.16rem;font-size:.7rem;color:rgba(255,255,255,.56)}
      #${ROOT_ID} .mpr-source-imdb .mpr-score{background:conic-gradient(#f5c518 calc(var(--score)*10%),rgba(255,255,255,.12) 0)}
      #${ROOT_ID} .mpr-source-douban .mpr-score{background:conic-gradient(#00b51d calc(var(--score)*10%),rgba(255,255,255,.12) 0)}
      #${ROOT_ID} .mpr-source-bangumi .mpr-score{background:conic-gradient(#f09199 calc(var(--score)*10%),rgba(255,255,255,.12) 0)}
      #${ROOT_ID} .mpr-source-rotten_tomatoes .mpr-score{background:conic-gradient(#fa320a calc(var(--score)*10%),rgba(255,255,255,.12) 0)}
      #${ROOT_ID} .mpr-source-metacritic .mpr-score{background:conic-gradient(#ffcc34 calc(var(--score)*10%),rgba(255,255,255,.12) 0)}
      #${ROOT_ID} .mpr-loading,#${ROOT_ID} .mpr-empty{padding:.8rem 1rem;border:1px dashed rgba(255,255,255,.18);border-radius:12px;color:rgba(255,255,255,.62);font-size:.82rem}
      @media (max-width:700px){#${ROOT_ID}{margin-top:.8rem}#${ROOT_ID} .mpr-grid{grid-template-columns:repeat(2,minmax(0,1fr))}#${ROOT_ID} .mpr-card{padding:.65rem;gap:.55rem}#${ROOT_ID} .mpr-score{flex-basis:39px;height:39px}#${ROOT_ID} .mpr-score:before{width:32px;height:32px}}
    `
    document.head.appendChild(style)
  }

  function paramsFromHash() {
    if (!location.hash.startsWith('#/media?')) return null
    const params = new URLSearchParams(location.hash.split('?', 2)[1] || '')
    const mediaId = params.get('mediaid') || ''
    const match = mediaId.match(/^tmdb:(\d+)$/)
    if (!match) return null
    const rawType = params.get('type') || ''
    return {
      tmdb_id: match[1],
      media_type: rawType === '电影' ? 'movie' : 'tv',
      title: params.get('title') || '',
      year: params.get('year') || '',
    }
  }

  function findMount() {
    const overview = document.querySelector('.media-overview')
    if (!overview || !overview.parentElement) return null
    return overview
  }

  function ensureRoot(mount) {
    let root = document.getElementById(ROOT_ID)
    if (!root) {
      root = document.createElement('section')
      root.id = ROOT_ID
      root.setAttribute('aria-label', '主流平台评分')
      mount.parentElement.insertBefore(root, mount)
    }
    return root
  }

  function render(root, payload) {
    const sources = Array.isArray(payload?.sources) ? payload.sources : []
    if (!sources.length) {
      root.innerHTML = '<div class="mpr-empty">暂未匹配到其他平台评分</div>'
      return
    }
    root.replaceChildren()
    const heading = document.createElement('h2')
    heading.className = 'mpr-heading'
    heading.textContent = payload.anime ? '主流评分 · 动漫' : '主流评分'
    const grid = document.createElement('div')
    grid.className = 'mpr-grid'
    for (const source of sources) {
      const card = document.createElement('a')
      card.className = `mpr-card ${sourceClass(source.id)}`
      card.href = source.url || '#'
      card.target = '_blank'
      card.rel = 'noopener noreferrer'
      card.style.setProperty('--score', String(Math.max(0, Math.min(10, Number(source.score) || 0))))
      const score = document.createElement('div')
      score.className = 'mpr-score'
      const scoreText = document.createElement('span')
      scoreText.textContent = source.display || Number(source.score).toFixed(1)
      score.appendChild(scoreText)
      const meta = document.createElement('div')
      meta.className = 'mpr-meta'
      const name = document.createElement('span')
      name.className = 'mpr-name'
      name.textContent = source.name
      const votes = document.createElement('span')
      votes.className = 'mpr-votes'
      votes.textContent = voteLabel(source.votes) || '点击查看来源'
      meta.append(name, votes)
      card.append(score, meta)
      grid.appendChild(card)
    }
    root.append(heading, grid)
  }

  async function refresh() {
    const params = paramsFromHash()
    if (!params) {
      document.getElementById(ROOT_ID)?.remove()
      lastKey = ''
      return
    }
    const key = `${params.media_type}:${params.tmdb_id}`
    const mount = findMount()
    if (!mount) return
    const currentState = document.getElementById(ROOT_ID)?.dataset.loaded
    if (key === lastKey && ['true', 'loading', 'error'].includes(currentState)) return
    lastKey = key
    const serial = ++requestSerial
    installStyle()
    const root = ensureRoot(mount)
    root.dataset.loaded = 'loading'
    root.innerHTML = '<div class="mpr-loading">正在汇总多平台评分…</div>'
    const query = new URLSearchParams(params)
    if (!params.year) query.delete('year')
    try {
      const response = await fetch(`${API}?${query.toString()}`, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const payload = await response.json()
      if (serial !== requestSerial || key !== lastKey) return
      render(root, payload)
      root.dataset.loaded = 'true'
    } catch (error) {
      if (serial !== requestSerial) return
      root.innerHTML = '<div class="mpr-empty">多源评分暂时不可用</div>'
      root.dataset.loaded = 'error'
      console.warn('[MediaRatings] rating request failed', error)
    }
  }

  const observer = new MutationObserver(() => window.requestAnimationFrame(refresh))
  observer.observe(document.documentElement, { childList: true, subtree: true })
  window.addEventListener('hashchange', () => {
    lastKey = ''
    refresh()
  })
  refresh()
})()
