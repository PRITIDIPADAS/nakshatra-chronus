"""Publish the observatory and the home page from frontend/ into site/ without rebuilding any data.

Run: python scripts/sync_site.py
"""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONT = os.path.join(ROOT, "frontend")
SITE = os.path.join(ROOT, "site")
PAGES = {"index.html": "observatory.html", "home.html": "index.html"}
ASSETS = ("style.css", "observatory.css", "observatory.js", "home.css", "home.js", "app.js", "charts.js", "next.js")


def site_links(html):
    """Inside the site the observatory is observatory.html and the home page is index.html."""
    return html.replace('href="index.html"', 'href="observatory.html"').replace('href="home.html"', 'href="index.html"')


def main():
    for src, dst in PAGES.items():
        html = open(os.path.join(FRONT, src)).read()
        if dst != "index.html":
            html = site_links(html)
        open(os.path.join(SITE, dst), "w").write(html)
    for name in ASSETS:
        shutil.copy(os.path.join(FRONT, name), os.path.join(SITE, name))
    print("published", ", ".join(list(PAGES.values()) + list(ASSETS)))


if __name__ == "__main__":
    main()
