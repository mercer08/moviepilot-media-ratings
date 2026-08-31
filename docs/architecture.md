# Architecture

```text
MoviePilot media page
        │
        │ optional reverse-proxy adapter
        ▼
MediaRatings /detail API
        │
        ├── MoviePilot TMDB module ── stable identity and base score
        ├── MoviePilot Douban chain ─ domestic score
        ├── IMDb / ImdbSource ─────── international score
        ├── Bangumi ───────────────── anime-only score
        └── OMDb ───────────────────── Rotten Tomatoes / Metacritic
```

The plugin keeps the aggregation API independent from presentation. Matching and normalization live in pure
helpers so they can be tested without importing the MoviePilot runtime. Only successful source collections are
cached; cache records contain public title and rating metadata, never user credentials or library data.

The reverse-proxy adapter is deliberately outside the plugin directory because MoviePilot V2 has no supported
media-detail extension point. This prevents marketplace upgrades from overwriting the host frontend.
