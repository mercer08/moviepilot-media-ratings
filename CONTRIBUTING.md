# Contributing

Bug reports should include the MoviePilot version, media identity (`tmdb_id`, type and year), expected sources,
and redacted plugin logs. Never attach tokens, API keys, cookies, internal URLs or database files.

Before opening a pull request, run:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile plugins.v2/mediaratings/__init__.py plugins.v2/mediaratings/client.py
node --check adapters/reverse-proxy/ratings.js
node --check adapters/reverse-proxy/service-worker.js
python3 tools/check_version.py
```

Keep the plugin runtime independent from the optional reverse-proxy adapter. New data sources must document
their public API or authorization requirement and include conservative matching tests.
