# 详情页多源评分

MoviePilot V2 插件后端。它按 TMDB 媒体身份并行聚合多平台评分，返回统一的 `0–10` 分制、
投票人数和来源链接，并将成功结果持久缓存。电视剧还支持按需查询季汇总评分与逐集评分。

## 数据源

- TMDB：MoviePilot 内建 TMDB 模块
- IMDb：优先读取公开标题接口，失败时复用已启用的 `ImdbSource` 插件能力
- 豆瓣：MoviePilot 内建豆瓣媒体链
- Bangumi：仅对识别为日语动画的条目查询公开 API
- Rotten Tomatoes / Metacritic：通过用户配置的 OMDb API Key 启用

## API

```text
GET /api/v1/plugin/MediaRatings/detail
GET /api/v1/plugin/MediaRatings/episodes
```

参数：

- `tmdb_id`：必填，正整数
- `media_type`：`movie` 或 `tv`
- `title`：可选，用于上游降级匹配
- `year`：可选，用于消除同名作品歧义

`episodes` 参数：

- `tmdb_id`：必填，电视剧的 TMDB ID
- `season`：必填，TMDB 季号，特别篇为 `0`

单集匹配以 TMDB 为锚点，综合标题、首播日期和集号查找 IMDb 候选，不要求不同平台
使用相同季号。季分数只汇总成功匹配且有评分的单集，有投票数时采用投票数加权平均。
Rotten Tomatoes 与 Metacritic 不提供稳定的公开逐集评分，因此不会出现在逐集结果中。

MoviePilot V2 没有向市场插件开放原生媒体详情页插槽。市场安装会提供评分聚合 API；如需把
评分卡嵌入 MoviePilot 原生详情页，请参阅仓库根目录的可选反向代理适配器说明。
