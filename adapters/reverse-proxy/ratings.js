(() => {
  'use strict'

  const loader = document.currentScript
  const API = loader?.dataset.api || '/api/v1/plugin/MediaRatings/detail'
  const EPISODE_API = loader?.dataset.episodesApi || API.replace(/\/detail$/, '/episodes')
  const CARD_API = loader?.dataset.cardApi || API.replace(/\/detail$/, '/card')
  const ROOT_ID = 'moviepilot-multi-source-ratings'
  const CARD_SELECTOR = '.media-card'
  const CARD_CONCURRENCY = 2
  let requestSerial = 0
  let lastKey = ''
  let activeCardRequests = 0
  const cardQueue = []
  const cardResponses = new Map()

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
      #${ROOT_ID}{--mpr-on-surface:var(--v-theme-on-surface,255,255,255);--mpr-surface:var(--v-theme-surface,32,36,44);margin:1rem 0 .25rem;grid-column:1/-1;color:rgb(var(--mpr-on-surface))}
      #${ROOT_ID} .mpr-heading{display:flex;align-items:center;gap:.5rem;margin:0 0 .7rem;font-size:1rem;font-weight:650;color:rgba(var(--mpr-on-surface),.92)}
      #${ROOT_ID} .mpr-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:.65rem}
      #${ROOT_ID} .mpr-card{position:relative;display:flex;align-items:center;gap:.7rem;min-height:66px;padding:.75rem .85rem;border:1px solid rgba(var(--mpr-on-surface),.14);border-radius:13px;background:rgba(var(--mpr-surface),.76);backdrop-filter:blur(12px);color:inherit;text-decoration:none;transition:transform .16s ease,border-color .16s ease,background .16s ease}
      #${ROOT_ID} .mpr-card:hover{transform:translateY(-2px);border-color:rgba(var(--mpr-on-surface),.3);background:rgb(var(--mpr-surface))}
      #${ROOT_ID} .mpr-score{display:grid;place-items:center;flex:0 0 43px;height:43px;border-radius:50%;background:conic-gradient(#8b5cf6 calc(var(--score)*10%),rgba(var(--mpr-on-surface),.12) 0);font-size:.92rem;font-weight:750;color:rgb(var(--mpr-on-surface))}
      #${ROOT_ID} .mpr-score{position:relative}
      #${ROOT_ID} .mpr-score:before{content:'';position:absolute;width:35px;height:35px;border-radius:50%;background:rgb(var(--mpr-surface))}
      #${ROOT_ID} .mpr-score span{position:relative;z-index:1}
      #${ROOT_ID} .mpr-meta{min-width:0;display:flex;flex-direction:column}
      #${ROOT_ID} .mpr-name{font-size:.83rem;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      #${ROOT_ID} .mpr-votes{margin-top:.16rem;font-size:.7rem;color:rgba(var(--mpr-on-surface),.6)}
      #${ROOT_ID} .mpr-source-imdb .mpr-score{background:conic-gradient(#f5c518 calc(var(--score)*10%),rgba(var(--mpr-on-surface),.12) 0)}
      #${ROOT_ID} .mpr-source-douban .mpr-score{background:conic-gradient(#00b51d calc(var(--score)*10%),rgba(var(--mpr-on-surface),.12) 0)}
      #${ROOT_ID} .mpr-source-bangumi .mpr-score{background:conic-gradient(#f09199 calc(var(--score)*10%),rgba(var(--mpr-on-surface),.12) 0)}
      #${ROOT_ID} .mpr-source-rotten_tomatoes .mpr-score{background:conic-gradient(#fa320a calc(var(--score)*10%),rgba(var(--mpr-on-surface),.12) 0)}
      #${ROOT_ID} .mpr-source-metacritic .mpr-score{background:conic-gradient(#ffcc34 calc(var(--score)*10%),rgba(var(--mpr-on-surface),.12) 0)}
      #${ROOT_ID} .mpr-loading,#${ROOT_ID} .mpr-empty{padding:.8rem 1rem;border:1px dashed rgba(var(--mpr-on-surface),.2);border-radius:12px;color:rgba(var(--mpr-on-surface),.66);font-size:.82rem}
      #${ROOT_ID} .mpr-seasons{margin-top:.8rem;border:1px solid rgba(var(--mpr-on-surface),.14);border-radius:13px;background:rgba(var(--mpr-surface),.58);overflow:hidden}
      #${ROOT_ID} .mpr-seasons summary{display:flex;align-items:center;gap:.5rem;padding:.8rem .9rem;cursor:pointer;font-size:.86rem;font-weight:650;list-style:none}
      #${ROOT_ID} .mpr-seasons summary::-webkit-details-marker{display:none}
      #${ROOT_ID} .mpr-seasons summary:after{content:'›';margin-left:auto;font-size:1.25rem;transform:rotate(90deg);transition:transform .16s ease}
      #${ROOT_ID} .mpr-seasons[open] summary:after{transform:rotate(-90deg)}
      #${ROOT_ID} .mpr-season-body{padding:0 .9rem .9rem}
      #${ROOT_ID} .mpr-season-toolbar{display:flex;align-items:center;gap:.55rem;margin-bottom:.7rem}
      #${ROOT_ID} .mpr-season-select{min-width:92px;padding:.42rem .6rem;border:1px solid rgba(var(--mpr-on-surface),.22);border-radius:8px;background:rgb(var(--mpr-surface));color:rgb(var(--mpr-on-surface));color-scheme:light dark}
      #${ROOT_ID} .mpr-season-score{margin-bottom:.7rem}
      #${ROOT_ID} .mpr-episode-list{display:grid;gap:.42rem}
      #${ROOT_ID} .mpr-episode{display:grid;grid-template-columns:minmax(150px,1fr) auto;align-items:center;gap:.75rem;padding:.58rem .68rem;border-radius:9px;background:rgba(var(--mpr-on-surface),.055)}
      #${ROOT_ID} .mpr-episode-title{min-width:0;font-size:.79rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      #${ROOT_ID} .mpr-episode-date{margin-left:.42rem;color:rgba(var(--mpr-on-surface),.52);font-size:.68rem}
      #${ROOT_ID} .mpr-episode-scores{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:.32rem}
      #${ROOT_ID} .mpr-chip{padding:.2rem .42rem;border:1px solid rgba(var(--mpr-on-surface),.16);border-radius:999px;color:rgba(var(--mpr-on-surface),.9);font-size:.67rem;text-decoration:none}
      #${ROOT_ID} .mpr-chip:hover{border-color:rgba(var(--mpr-on-surface),.36)}
      .mpr-card-ratings{position:absolute;z-index:5;left:.38rem;right:.38rem;bottom:.38rem;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.22rem;pointer-events:none}
      .mpr-card-rating{display:inline-flex;align-items:center;justify-content:center;gap:.18rem;min-width:0;min-height:20px;padding:.12rem .2rem;border:1px solid rgba(255,255,255,.2);border-radius:999px;background:rgba(12,15,20,.78);box-shadow:0 1px 4px rgba(0,0,0,.28);color:#fff;font-size:.6rem;font-weight:700;line-height:1;white-space:nowrap;overflow:hidden;backdrop-filter:blur(7px)}
      .mpr-card-rating:before{content:'';width:.34rem;height:.34rem;border-radius:50%;background:#8b5cf6}
      .mpr-card-rating[data-source="imdb"]:before{background:#f5c518}.mpr-card-rating[data-source="douban"]:before{background:#00b51d}.mpr-card-rating[data-source="bangumi"]:before{background:#f09199}.mpr-card-rating[data-source="rotten_tomatoes"]:before{background:#fa320a}.mpr-card-rating[data-source="metacritic"]:before{background:#ffcc34}
      @media (max-width:700px){#${ROOT_ID}{margin-top:.8rem}#${ROOT_ID} .mpr-grid{grid-template-columns:repeat(2,minmax(0,1fr))}#${ROOT_ID} .mpr-card{padding:.65rem;gap:.55rem}#${ROOT_ID} .mpr-score{flex-basis:39px;height:39px}#${ROOT_ID} .mpr-score:before{width:32px;height:32px}#${ROOT_ID} .mpr-episode{grid-template-columns:1fr;gap:.42rem}#${ROOT_ID} .mpr-episode-scores{justify-content:flex-start}}
    `
    document.head.appendChild(style)
  }

  function cardMeta(card) {
    const title = card.querySelector('.media-card-title')?.textContent?.trim() || ''
    if (!title) return null
    const typeLabels = [...card.querySelectorAll('.v-chip__content')]
      .map(node => node.textContent?.trim().toLowerCase() || '')
    let mediaType = ''
    if (typeLabels.some(value => ['电影', 'movie', 'film'].includes(value))) mediaType = 'movie'
    if (typeLabels.some(value => ['电视剧', '剧集', '动漫', 'tv', 'series'].includes(value))) mediaType = 'tv'
    if (!mediaType) return null
    const yearText = card.querySelector('.v-card-text span')?.textContent || card.textContent || ''
    const yearMatch = yearText.match(/\b(19|20)\d{2}\b/)
    const year = yearMatch ? yearMatch[0] : ''
    return { title, year, media_type: mediaType }
  }

  function cardKey(meta) {
    return `${meta.media_type}:${meta.title}:${meta.year}`
  }

  function sourceShortName(source) {
    return ({
      imdb: 'IMDb', douban: '豆瓣', bangumi: 'BGM',
      rotten_tomatoes: 'RT', metacritic: 'MC', tmdb: 'TMDB',
    })[source.id] || source.name || source.id
  }

  function renderCardRatings(card, payload, key) {
    if (!card.isConnected || card.dataset.mprCardKey !== key) return
    card.querySelector('.mpr-card-ratings')?.remove()
    const sourceOrder = ['imdb', 'douban', 'bangumi', 'rotten_tomatoes', 'metacritic', 'tmdb']
    const sourcePriority = source => {
      const index = sourceOrder.indexOf(source.id)
      return index < 0 ? sourceOrder.length : index
    }
    const sources = (Array.isArray(payload?.sources) ? payload.sources : [])
      .filter(source => source?.id && source?.score !== null && source?.score !== undefined)
      .sort((left, right) => sourcePriority(left) - sourcePriority(right))
    const external = sources.filter(source => source.id !== 'tmdb')
    const visible = (external.length ? external : sources).slice(0, 4)
    if (!visible.length) {
      card.dataset.mprCardState = 'empty'
      return
    }
    const group = document.createElement('div')
    group.className = 'mpr-card-ratings'
    group.setAttribute('aria-label', '多平台评分')
    for (const source of visible) {
      const chip = document.createElement('span')
      chip.className = 'mpr-card-rating'
      chip.dataset.source = source.id
      chip.textContent = `${sourceShortName(source)} ${source.display || Number(source.score).toFixed(1)}`
      chip.title = `${source.name || sourceShortName(source)}：${source.display || source.score}`
      group.appendChild(chip)
    }
    card.appendChild(group)
    card.dataset.mprCardState = 'loaded'
  }

  async function fetchCard(meta) {
    const query = new URLSearchParams(meta)
    if (!meta.year) query.delete('year')
    const response = await fetch(`${CARD_API}?${query}`, {
      credentials: 'same-origin', headers: { Accept: 'application/json' },
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return response.json()
  }

  function drainCardQueue() {
    while (activeCardRequests < CARD_CONCURRENCY && cardQueue.length) {
      const task = cardQueue.shift()
      activeCardRequests += 1
      fetchCard(task.meta)
        .then(payload => {
          task.resolve(payload)
          document.querySelectorAll(CARD_SELECTOR).forEach(card => {
            if (card.dataset.mprCardKey === task.key) renderCardRatings(card, payload, task.key)
          })
        })
        .catch(error => {
          cardResponses.delete(task.key)
          task.reject(error)
          console.info('[MediaRatings] card rating unavailable', task.meta.title, error)
        })
        .finally(() => {
          activeCardRequests -= 1
          drainCardQueue()
        })
    }
  }

  function requestCard(meta) {
    const key = cardKey(meta)
    if (!cardResponses.has(key)) {
      cardResponses.set(key, new Promise((resolve, reject) => {
        cardQueue.push({ key, meta, resolve, reject })
        drainCardQueue()
      }))
    }
    return cardResponses.get(key)
  }

  async function hydrateCard(card) {
    const meta = cardMeta(card)
    if (!meta) return
    const key = cardKey(meta)
    if (card.dataset.mprCardKey !== key) {
      card.querySelector('.mpr-card-ratings')?.remove()
      card.dataset.mprCardKey = key
      card.dataset.mprCardState = ''
    }
    if (['loading', 'loaded', 'empty'].includes(card.dataset.mprCardState)) return
    card.dataset.mprCardState = 'loading'
    try {
      const payload = await requestCard(meta)
      renderCardRatings(card, payload, key)
    } catch (_) {
      if (card.dataset.mprCardKey === key) card.dataset.mprCardState = 'error'
    }
  }

  const cardObserver = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue
      cardObserver.unobserve(entry.target)
      hydrateCard(entry.target)
    }
  }, { rootMargin: '180px 0px' })

  function scanCards() {
    installStyle()
    document.querySelectorAll(CARD_SELECTOR).forEach(card => {
      const meta = cardMeta(card)
      if (!meta) return
      const key = cardKey(meta)
      if (card.dataset.mprCardKey !== key) {
        card.querySelector('.mpr-card-ratings')?.remove()
        card.dataset.mprCardKey = key
        card.dataset.mprCardState = ''
      }
      if (!['loading', 'loaded', 'empty'].includes(card.dataset.mprCardState)) {
        cardObserver.observe(card)
      }
    })
  }

  function paramsFromHash() {
    if (!location.hash.startsWith('#/media?')) return null
    const params = new URLSearchParams(location.hash.split('?', 2)[1] || '')
    const mediaId = params.get('mediaid') || ''
    const match = mediaId.match(/^tmdb:(\d+)$/)
    if (!match) return null
    const rawType = (params.get('type') || '').trim().toLowerCase()
    const movieTypes = new Set(['电影', 'movie', 'film'])
    return {
      tmdb_id: match[1],
      media_type: movieTypes.has(rawType) ? 'movie' : 'tv',
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

  function sourceCard(source) {
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
    votes.textContent = voteLabel(source.votes) || (source.episodes ? `${source.episodes} 集` : '点击查看来源')
    meta.append(name, votes)
    card.append(score, meta)
    return card
  }

  function renderSeasonResult(target, payload) {
    target.replaceChildren()
    const sources = Array.isArray(payload?.sources) ? payload.sources : []
    if (sources.length) {
      const grid = document.createElement('div')
      grid.className = 'mpr-grid mpr-season-score'
      for (const source of sources) grid.appendChild(sourceCard(source))
      target.appendChild(grid)
    }
    const episodes = Array.isArray(payload?.episodes) ? payload.episodes : []
    if (!episodes.length) {
      const empty = document.createElement('div')
      empty.className = 'mpr-empty'
      empty.textContent = '这一季暂未匹配到单集信息'
      target.appendChild(empty)
      return
    }
    const list = document.createElement('div')
    list.className = 'mpr-episode-list'
    for (const episode of episodes) {
      const row = document.createElement('div')
      row.className = 'mpr-episode'
      const title = document.createElement('div')
      title.className = 'mpr-episode-title'
      title.textContent = `E${String(episode.episode || 0).padStart(2, '0')} · ${episode.title || '未命名'}`
      if (episode.air_date) {
        const date = document.createElement('span')
        date.className = 'mpr-episode-date'
        date.textContent = episode.air_date
        title.appendChild(date)
      }
      const scores = document.createElement('div')
      scores.className = 'mpr-episode-scores'
      for (const source of episode.sources || []) {
        const chip = document.createElement('a')
        chip.className = `mpr-chip ${sourceClass(source.id)}`
        chip.href = source.url || '#'
        chip.target = '_blank'
        chip.rel = 'noopener noreferrer'
        chip.textContent = `${source.name} ${source.display || Number(source.score).toFixed(1)}`
        scores.appendChild(chip)
      }
      if (!scores.childElementCount) scores.textContent = '暂无评分'
      row.append(title, scores)
      list.appendChild(row)
    }
    target.appendChild(list)
  }

  function episodePanel(payload) {
    const seasons = (Array.isArray(payload?.seasons) ? payload.seasons : [])
      .map(Number).filter(Number.isInteger).sort((a, b) => a - b)
    if (payload?.media_type !== 'tv' || !seasons.length) return null
    const panel = document.createElement('details')
    panel.className = 'mpr-seasons'
    const summary = document.createElement('summary')
    summary.textContent = '季 / 单集评分'
    const body = document.createElement('div')
    body.className = 'mpr-season-body'
    const toolbar = document.createElement('div')
    toolbar.className = 'mpr-season-toolbar'
    const select = document.createElement('select')
    select.className = 'mpr-season-select'
    select.setAttribute('aria-label', '选择季')
    for (const season of seasons) {
      const option = document.createElement('option')
      option.value = String(season)
      option.textContent = season === 0 ? '特别篇' : `第 ${season} 季`
      select.appendChild(option)
    }
    const initial = seasons.find(value => value > 0) ?? seasons[0]
    select.value = String(initial)
    const status = document.createElement('span')
    status.className = 'mpr-votes'
    status.textContent = '展开后按需加载'
    const result = document.createElement('div')
    toolbar.append(select, status)
    body.append(toolbar, result)
    panel.append(summary, body)

    let loadedSeason = null
    let loadSerial = 0
    const load = async () => {
      const season = Number(select.value)
      if (!Number.isInteger(season) || loadedSeason === season) return
      const serial = ++loadSerial
      status.textContent = '正在匹配 IMDb 与 TMDB…'
      result.innerHTML = '<div class="mpr-loading">正在加载季与单集评分…</div>'
      try {
        const query = new URLSearchParams({ tmdb_id: payload.tmdb_id, season })
        const response = await fetch(`${EPISODE_API}?${query}`, {
          credentials: 'same-origin', headers: { Accept: 'application/json' },
        })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        const data = await response.json()
        if (serial !== loadSerial) return
        loadedSeason = season
        status.textContent = '季评分按已匹配单集汇总'
        renderSeasonResult(result, data)
      } catch (error) {
        if (serial !== loadSerial) return
        status.textContent = '加载失败，可切换季重试'
        result.innerHTML = '<div class="mpr-empty">季与单集评分暂时不可用</div>'
        console.warn('[MediaRatings] episode request failed', error)
      }
    }
    panel.addEventListener('toggle', () => { if (panel.open) load() })
    select.addEventListener('change', load)
    return panel
  }

  function render(root, payload) {
    const sources = Array.isArray(payload?.sources) ? payload.sources : []
    root.replaceChildren()
    const heading = document.createElement('h2')
    heading.className = 'mpr-heading'
    heading.textContent = payload.anime ? '主流评分 · 动漫' : '主流评分'
    root.appendChild(heading)
    if (sources.length) {
      const grid = document.createElement('div')
      grid.className = 'mpr-grid'
      for (const source of sources) grid.appendChild(sourceCard(source))
      root.appendChild(grid)
    } else {
      const empty = document.createElement('div')
      empty.className = 'mpr-empty'
      empty.textContent = '暂未匹配到其他平台评分'
      root.appendChild(empty)
    }
    const seasons = episodePanel(payload)
    if (seasons) root.appendChild(seasons)
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

  let scanPending = false
  const scheduleRefresh = () => {
    if (scanPending) return
    scanPending = true
    window.requestAnimationFrame(() => {
      scanPending = false
      refresh()
      scanCards()
    })
  }
  const observer = new MutationObserver(scheduleRefresh)
  observer.observe(document.documentElement, { childList: true, characterData: true, subtree: true })
  window.addEventListener('hashchange', () => {
    lastKey = ''
    scheduleRefresh()
  })
  refresh()
  scanCards()
})()
