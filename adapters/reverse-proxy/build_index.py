#!/usr/bin/env python3
"""Build a MoviePilot V2 index that loads the optional ratings adapter."""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.request import Request, urlopen


VERSION = "1.5.2"
TAG = (
    f'<script defer src="/moviepilot-ratings/ratings.js?v={VERSION}" '
    'data-api="/moviepilot-ratings/api/detail" '
    'data-episodes-api="/moviepilot-ratings/api/episodes" '
    'data-card-api="/moviepilot-ratings/api/card"></script>'
)


def inject(html: str) -> str:
    """Insert the adapter once immediately before the closing head tag."""

    if "/moviepilot-ratings/ratings.js" in html:
        raise ValueError("ratings adapter is already present in the source index")
    marker = "</head>"
    if marker not in html:
        raise ValueError("source index has no closing head tag")
    return html.replace(marker, f"{TAG}\n{marker}", 1)


def fetch(url: str) -> str:
    """Fetch the current upstream MoviePilot index without sending credentials."""

    request = Request(url, headers={"User-Agent": "MoviePilot-MediaRatings-Adapter/1.5"})
    with urlopen(request, timeout=20) as response:  # noqa: S310 - operator supplies the trusted upstream URL
        return response.read().decode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="MoviePilot upstream index URL")
    parser.add_argument("--output", required=True, type=Path, help="generated index path")
    args = parser.parse_args()

    generated = inject(fetch(args.source))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(generated, encoding="utf-8")
    print(f"generated {args.output} with ratings adapter {VERSION}")


if __name__ == "__main__":
    main()
