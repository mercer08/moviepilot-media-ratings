# V2 原生媒体页面适配器

> 这是可选的高级部署方式，不属于 MoviePilot 标准插件接口。操作前请备份反向代理配置与生成的
> `index.html`。MoviePilot 前端升级后需要重新生成注入后的首页。

适配器完成四件事：

1. 从 MoviePilot 上游取得当前 `index.html`，在 `</head>` 前加入 `ratings.js`。
2. 用独立的 `/moviepilot-ratings/api/detail`、`/moviepilot-ratings/api/episodes` 与
   `/moviepilot-ratings/api/card` 转发插件 API，
   避开 V2 Service Worker 的 `/api/` 缓存。
3. 由反向代理直接提供注入后的首页和 `ratings.js`。
4. 可选接管根 Service Worker，清除旧 API/预缓存后再导入 MoviePilot 原始 Service Worker。

生成首页：

```bash
python3 adapters/reverse-proxy/build_index.py \
  --source http://moviepilot:3000/ \
  --output /srv/moviepilot-media-ratings/index.html
```

把 `ratings.js` 与 `service-worker.js` 复制到同一只读静态目录，并参照
[`Caddyfile.example`](../adapters/reverse-proxy/Caddyfile.example) 合并路由。示例中的
`moviepilot:3000` 和 `/srv/moviepilot-media-ratings` 应替换为自己的容器地址与挂载路径。

验收至少包括：

```bash
curl -fsS 'https://YOUR_HOST/moviepilot-ratings/api/detail?tmdb_id=93544&media_type=tv&title=Top%20Boy&year=2019'
curl -fsS 'https://YOUR_HOST/moviepilot-ratings/api/episodes?tmdb_id=93544&season=1'
curl -fsS 'https://YOUR_HOST/moviepilot-ratings/api/card?title=Top%20Boy&media_type=tv&year=2019'
curl -fsS 'https://YOUR_HOST/' | grep -F '/moviepilot-ratings/ratings.js?v=1.5.2'
```

然后分别打开电影、普通电视剧、动漫详情页、推荐页、搜索结果与豆瓣/IMDb/MAL 榜单，并在
白色/深色主题间切换。滚动长榜单时，卡片评分应在进入可视区域后逐步出现。
还需从豆瓣等非 TMDB 榜单点击进入详情页，确认 `mediaid=douban:*` 这类 URL 会按标题、年份与
类型回退解析并显示完整评分。
电视剧需展开“季 / 单集评分”并切换不同季，检查来源、链接、加载状态、文字对比度与横向溢出。
季与单集数据只在首次展开或切换季时加载。
