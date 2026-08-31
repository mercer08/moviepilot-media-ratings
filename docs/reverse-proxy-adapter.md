# V2 原生详情页适配器

> 这是可选的高级部署方式，不属于 MoviePilot 标准插件接口。操作前请备份反向代理配置与生成的
> `index.html`。MoviePilot 前端升级后需要重新生成注入后的首页。

适配器完成四件事：

1. 从 MoviePilot 上游取得当前 `index.html`，在 `</head>` 前加入 `ratings.js`。
2. 用独立的 `/moviepilot-ratings/api/detail` 与 `/moviepilot-ratings/api/episodes` 转发插件 API，
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
curl -fsS 'https://YOUR_HOST/' | grep -F '/moviepilot-ratings/ratings.js?v=1.3.0'
```

然后分别打开普通电视剧、动漫详情页及 390px 宽移动端页面，展开“季 / 单集评分”，切换不同季，
检查来源、链接、加载状态与横向溢出。季与单集数据只在首次展开或切换季时加载。
