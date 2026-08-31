# MoviePilot 详情页多源评分

为 MoviePilot V2 聚合 TMDB、IMDb、TVmaze、豆瓣等主流评分；识别为动漫时追加 Bangumi，
配置 OMDb API Key 后还可显示 Rotten Tomatoes 与 Metacritic。

![MoviePilot V2](https://img.shields.io/badge/MoviePilot-2.15.1%2B-7c3aed)
![License](https://img.shields.io/badge/license-MIT-green)

## 功能

- 以 TMDB ID 为稳定主键，结合原始标题、年份和媒体类型消除同名误匹配
- 电视剧支持季汇总分与逐集评分，展开后按需加载，不拖慢作品详情首屏
- 不强行按季号对齐：通过单集标题、首播日期和集号匹配 IMDb / TVmaze，兼容续作季号差异
- 并行读取多个公开数据源，统一为 `0–10` 分制
- 返回投票人数和可点击的来源链接
- 日语动画自动追加 Bangumi，普通影视不发起 Bangumi 请求
- 成功结果持久缓存 1–168 小时，上游短暂异常时避免重复请求
- 可选响应式评分卡：桌面自动分栏，窄屏固定两列，无横向溢出
- 不需要数据库迁移，也不安装额外 Python 包

## 安装

要求 MoviePilot `2.15.1` 或更新的 V2 版本。

1. 在 MoviePilot 的插件仓库设置中添加：

   ```text
   https://github.com/mercer08/moviepilot-media-ratings
   ```

2. 刷新插件市场，安装“详情页多源评分”。
3. 打开插件设置并启用。缓存默认 12 小时。
4. 如需 Rotten Tomatoes 与 Metacritic，在设置中填写自己的 OMDb API Key。

安装到这里即获得标准 MoviePilot 插件 API：

```text
GET /api/v1/plugin/MediaRatings/detail?tmdb_id=93544&media_type=tv&title=Top%20Boy&year=2019
GET /api/v1/plugin/MediaRatings/episodes?tmdb_id=93544&season=1
```

## 关于“详情页”显示

MoviePilot V2 的标准插件合同可以注册 API、配置页、插件数据页、仪表盘和系统模块，但没有给
原生媒体详情页提供前端扩展插槽。因此，本仓库把实现明确分成两层：

1. `plugins.v2/mediaratings/`：完全标准的市场插件，负责查询、匹配、归一化和缓存。
2. `adapters/reverse-proxy/`：可选前端适配器，把评分卡插入原生详情页；它需要反向代理配合，
   不属于 MoviePilot 标准插件生命周期。

这种边界是刻意保留的：插件安装和升级不会偷偷覆盖 MoviePilot 前端文件。需要与当前已验收
页面相同的评分卡时，请按 [反向代理适配器说明](docs/reverse-proxy-adapter.md) 部署。

## 实现方式

请求进入插件后，先通过 MoviePilot 的 TMDB 模块解析标准标题、原始标题、年份、IMDb ID、
TVDB ID、语言、国家和类型。随后并行查询 TVmaze、豆瓣和（仅动漫）Bangumi，再查询 IMDb；
配置 OMDb 时补充影评聚合站评分。候选匹配使用标题规范化、相似度、年份与媒体类型共同判定，
低置信度结果直接丢弃，避免“有分但作品错了”。

季与单集接口以 TMDB 的单集清单为锚点，再把 IMDb 和 TVmaze 的候选集按标题、完整首播日期及
集号评分匹配。匹配过程不把季号当作唯一依据，例如 2019 版《上层男孩》在 TMDB 的第 1 季可
正确对应 IMDb 延续旧版编号后的第 3 季。季评分由已匹配的单集评分汇总；有投票数的平台使用
投票数加权平均，否则使用算术平均，并在返回中给出实际参与汇总的集数。

返回示例：

```json
{
  "tmdb_id": 93544,
  "media_type": "tv",
  "anime": false,
  "sources": [
    {"id": "tmdb", "name": "TMDB", "score": 8.0, "votes": 162, "url": "..."},
    {"id": "imdb", "name": "IMDb", "score": 8.4, "votes": 50000, "url": "..."}
  ]
}
```

单季返回示例：

```json
{
  "tmdb_id": 93544,
  "season": 1,
  "sources": [
    {"id": "imdb", "name": "IMDb", "score": 8.4, "votes": 7698, "episodes": 10}
  ],
  "episodes": [
    {
      "season": 1,
      "episode": 1,
      "title": "Bruk Up",
      "sources": [
        {"id": "tmdb", "name": "TMDB", "score": 7.8},
        {"id": "imdb", "name": "IMDb", "score": 7.8}
      ]
    }
  ]
}
```

## 数据与隐私

插件只向所列评分平台发送作品标识、标题、年份和媒体类型，不读取或上传 MoviePilot 账号、
媒体库文件、订阅记录、下载记录、Cookie 或服务器地址。OMDb API Key 保存在 MoviePilot 插件
配置中，不写入仓库或日志。

评分属于第三方数据，各平台名称和商标归各自权利人所有；本项目与这些平台没有隶属关系。

## 开发

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile plugins.v2/mediaratings/__init__.py plugins.v2/mediaratings/client.py
node --check adapters/reverse-proxy/ratings.js
python3 tools/check_version.py
```

许可证：[MIT](LICENSE)
