#!/usr/bin/env python3
"""
Nofakey.ai site builder.

Scans the repo's blog/ folder for post HTML files, pulls metadata out of
each post's own <title>, meta description, and Article JSON-LD block, and
uses it to regenerate:

  - index.html   -> "Latest from the blog" preview (top 3 posts)
  - blog.html    -> full blog listing grid
  - sitemap.xml  -> XML sitemap for search engines
  - sitemap.html -> human-readable sitemap page
  - rss.xml      -> RSS 2.0 feed of posts
  - llms.txt     -> plain-text site summary for AI crawlers (llmstxt.org)

Run this locally with `python3 scripts/build_site.py`, or let the GitHub
Action in .github/workflows/update-site.yml run it automatically on every
push that touches an .html file.

HOW TO ADD A NEW BLOG POST
---------------------------
1. Copy blog/how-to-check-if-a-whatsapp-message-is-fake.html as a starting
   template and save it under a new filename inside the blog/ folder, e.g.
   blog/how-to-spot-a-fake-prize-message.html
2. Update its <title>, <meta name="description">, and the "Article"
   JSON-LD block (headline, description, datePublished, dateModified, and
   the canonical/og:url, which should read
   https://nofakey-ai.github.io/blog/<your-filename>.html).
3. Optionally set this meta tag to control the card's color theme:
     <meta name="thumb-theme" content="t2"/>   (t1 = violet, t2 = red/orange, t3 = green)
   Each theme automatically gets a matching animated icon badge — no image
   or emoji needed.
4. Commit and push. The workflow does the rest.
"""

import glob
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from email.utils import format_datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_DIR = os.path.join(ROOT, "blog")
SITE_URL = "https://nofakey-ai.github.io"
SITE_NAME = "Nofakey.ai"

STATIC_PAGES = {"index.html", "blog.html", "about.html", "contact.html", "sitemap.html"}
MAX_PREVIEW = 3

# Each thumbnail theme gets a matching animated icon badge instead of an emoji.
THEME_ICONS = {
    "t1": "ti-zoom-scan",       # violet — guides / how-to-check
    "t2": "ti-alert-triangle",  # red/orange — scam & alert posts
    "t3": "ti-shield-check",    # green — verification / trust posts
}
DEFAULT_THEME = "t1"


# ---------------------------------------------------------------- helpers --

def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def meta_name(html, name):
    m = re.search(rf'<meta name="{re.escape(name)}" content="(.*?)"\s*/?>', html)
    return m.group(1) if m else None


def meta_prop(html, prop):
    m = re.search(rf'<meta property="{re.escape(prop)}" content="(.*?)"\s*/?>', html)
    return m.group(1) if m else None


def extract_title(html):
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    if not m:
        return "Untitled"
    t = m.group(1).strip()
    return re.sub(r"\s*[\|\u2013-]\s*Nofakey\.ai\s*$", "", t).strip()


def extract_article_field(html, field):
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            data = json.loads(block)
        except Exception:
            continue
        if isinstance(data, dict) and data.get("@type") == "Article":
            return data.get(field)
    return None


def git_date(path):
    """Fall back to the first git commit date that added this file."""
    rel = os.path.relpath(path, ROOT)
    try:
        out = subprocess.check_output(
            ["git", "log", "--follow", "--format=%aI", "--", rel],
            cwd=ROOT, stderr=subprocess.DEVNULL,
        ).decode().strip()
        if out:
            return out.splitlines()[-1]  # earliest commit touching the file
    except Exception:
        pass
    return datetime.now(timezone.utc).isoformat()


def to_rfc822(iso_date):
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except Exception:
        dt = datetime.now(timezone.utc)
    return format_datetime(dt)


# ------------------------------------------------------------- collection --

def collect_posts():
    posts = []
    if not os.path.isdir(POSTS_DIR):
        return posts
    for path in sorted(glob.glob(os.path.join(POSTS_DIR, "*.html"))):
        base = os.path.basename(path)
        html = read(path)
        title = extract_article_field(html, "headline") or extract_title(html)
        description = meta_name(html, "description") or ""
        tag = meta_prop(html, "article:section") or "Guide"
        theme = meta_name(html, "thumb-theme") or DEFAULT_THEME
        if theme not in THEME_ICONS:
            theme = DEFAULT_THEME
        date = extract_article_field(html, "datePublished") or git_date(path)
        posts.append({
            "file": f"blog/{base}",       # root-relative href, used by index.html / blog.html cards
            "url": f"{SITE_URL}/blog/{base}",  # absolute URL, used by sitemap / RSS / llms.txt
            "title": title,
            "description": description,
            "tag": tag,
            "theme": theme,
            "date": date,
        })
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


# -------------------------------------------------------------- renderers --

def render_card(post, with_readmore=True):
    readmore = (
        '<span class="blog-readmore">Read the guide <i class="ti ti-arrow-right"></i></span>'
        if with_readmore else ""
    )
    icon = THEME_ICONS.get(post["theme"], THEME_ICONS[DEFAULT_THEME])
    return f"""      <a class="blog-card" href="{post['file']}">
        <div class="blog-thumb {post['theme']}">
          <div class="shine"></div>
          <div class="blog-thumb-icon-float"><span class="blog-thumb-icon-wrap"><i class="ti {icon}"></i></span></div>
        </div>
        <div class="blog-body">
          <div class="blog-tag">{post['tag']}</div>
          <h3>{post['title']}</h3>
          <p>{post['description']}</p>
          {readmore}
        </div>
      </a>"""


def replace_between(content, start_marker, end_marker, new_inner):
    pattern = re.compile(re.escape(start_marker) + r".*?" + re.escape(end_marker), re.S)
    replacement = f"{start_marker}\n{new_inner}\n      {end_marker}"
    if not pattern.search(content):
        raise RuntimeError(f"Markers {start_marker} / {end_marker} not found")
    return pattern.sub(replacement, content)


def update_blog_listing(posts):
    path = os.path.join(ROOT, "blog.html")
    content = read(path)
    if posts:
        inner = "\n".join(render_card(p) for p in posts)
    else:
        inner = '      <p style="color:var(--gray-600);">No posts yet — check back soon.</p>'
    content = replace_between(content, "<!-- BLOG_LIST_START (auto-generated — do not edit between the markers by hand) -->",
                               "<!-- BLOG_LIST_END -->", inner)
    write(path, content)


def update_homepage_preview(posts):
    path = os.path.join(ROOT, "index.html")
    content = read(path)
    preview = posts[:MAX_PREVIEW]
    if preview:
        inner = "\n".join(render_card(p) for p in preview)
    else:
        inner = '      <p style="color:var(--gray-600);">No posts yet — check back soon.</p>'
    content = replace_between(content, "<!-- BLOG_PREVIEW_START -->", "<!-- BLOG_PREVIEW_END -->", inner)
    write(path, content)


def update_sitemap_xml(posts):
    static_urls = [
        (f"{SITE_URL}/", "weekly", "1.0"),
        (f"{SITE_URL}/blog.html", "weekly", "0.8"),
        (f"{SITE_URL}/about.html", "monthly", "0.5"),
        (f"{SITE_URL}/contact.html", "monthly", "0.5"),
    ]
    entries = []
    for url, freq, priority in static_urls:
        entries.append(f"  <url>\n    <loc>{url}</loc>\n    <changefreq>{freq}</changefreq>\n    <priority>{priority}</priority>\n  </url>")
    for p in posts:
        lastmod = p["date"][:10]
        entries.append(
            f"  <url>\n    <loc>{p['url']}</loc>\n    <lastmod>{lastmod}</lastmod>"
            f"\n    <changefreq>monthly</changefreq>\n    <priority>0.7</priority>\n  </url>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries) + "\n</urlset>\n"
    )
    write(os.path.join(ROOT, "sitemap.xml"), xml)


def update_sitemap_html(posts):
    post_items = "\n".join(
        f'          <li><a href="{p["file"]}">{p["title"]}</a> <span class="sm-date">{p["date"][:10]}</span></li>'
        for p in posts
    ) or "          <li>No posts yet.</li>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Sitemap | Nofakey.ai</title>
  <meta name="description" content="A full, human-readable list of every page on Nofakey.ai."/>
  <link rel="canonical" href="{SITE_URL}/sitemap.html"/>
  <meta name="robots" content="index, follow"/>
  <link rel="icon" href="favicon.svg" type="image/svg+xml"/>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Syne:wght@700;800&display=swap" rel="stylesheet"/>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@latest/tabler-icons.min.css"/>
  <link rel="stylesheet" href="shared.css"/>
  <style>
    .sm-list {{ list-style: none; display: flex; flex-direction: column; gap: 10px; }}
    .sm-list li {{ font-size: 15px; }}
    .sm-list a {{ color: var(--blue); text-decoration: none; font-weight: 500; }}
    .sm-list a:hover {{ text-decoration: underline; }}
    .sm-date {{ color: var(--gray-400); font-size: 12px; margin-left: 8px; }}
    .sm-group {{ margin-bottom: 2.5rem; }}
    .sm-group h2 {{ font-family:'Syne',sans-serif; font-size: 1.1rem; margin-bottom: 1rem; color: var(--gray-900); }}
  </style>
</head>
<body>

<nav>
  <a href="index.html" class="logo">
    <div class="logo-icon"><i class="ti ti-shield-check"></i></div>
    <span class="logo-text">Nofakey<span>.ai</span></span>
  </a>
  <ul class="nav-links">
    <li><a href="index.html#how">How it works</a></li>
    <li><a href="blog.html">Blog</a></li>
    <li><a href="about.html">About</a></li>
    <li><a href="contact.html">Contact</a></li>
  </ul>
  <div style="display:flex; align-items:center; gap:12px;">
    <a href="index.html#checker" class="nav-cta">Check now — free</a>
    <button class="nav-toggle" id="navToggle" aria-label="Open menu" aria-expanded="false" aria-controls="mobileMenu">
      <i class="ti ti-menu-2"></i>
    </button>
  </div>
</nav>
<div class="mobile-menu" id="mobileMenu">
  <a href="index.html#how">How it works</a>
  <a href="blog.html">Blog</a>
  <a href="about.html">About</a>
  <a href="contact.html">Contact</a>
</div>

<main>
<section class="page-hero">
  <div class="section-eyebrow" style="color:#93C5FD;">Sitemap</div>
  <h1>Every page on Nofakey.ai</h1>
  <p>A full, human-readable index — auto-generated and always up to date.</p>
</section>

<section>
  <div class="section-inner">
    <div class="sm-group">
      <h2>Pages</h2>
      <ul class="sm-list">
        <li><a href="index.html">Home</a></li>
        <li><a href="blog.html">Blog</a></li>
        <li><a href="about.html">About</a></li>
        <li><a href="contact.html">Contact</a></li>
      </ul>
    </div>
    <div class="sm-group">
      <h2>Blog posts</h2>
      <ul class="sm-list">
{post_items}
      </ul>
    </div>
  </div>
</section>
</main>

<footer>
  <div class="footer-bottom" style="border-top:none; padding-top:0;">
    <p>© 2026 Nofakey.ai — All rights reserved</p>
  </div>
</footer>

<script src="shared.js"></script>
</body>
</html>
"""
    write(os.path.join(ROOT, "sitemap.html"), html)


def update_rss(posts):
    now_rfc822 = format_datetime(datetime.now(timezone.utc))
    items = []
    for p in posts:
        items.append(f"""    <item>
      <title>{p['title']}</title>
      <link>{p['url']}</link>
      <guid>{p['url']}</guid>
      <pubDate>{to_rfc822(p['date'])}</pubDate>
      <description><![CDATA[{p['description']}]]></description>
    </item>""")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{SITE_NAME} Blog</title>
    <link>{SITE_URL}/blog.html</link>
    <description>Guides on spotting fake news, scams, and misinformation before you share them.</description>
    <language>en-us</language>
    <lastBuildDate>{now_rfc822}</lastBuildDate>
{chr(10).join(items)}
  </channel>
</rss>
"""
    write(os.path.join(ROOT, "rss.xml"), xml)


def update_llms_txt(posts):
    post_lines = "\n".join(f"- [{p['title']}]({p['url']}): {p['description']}" for p in posts) or "- (no posts yet)"
    txt = f"""# {SITE_NAME}

> A free, privacy-first tool that checks WhatsApp messages, emails, and news
> text for common scam and misinformation wording patterns. Not a full
> fact-checking service — a fast first-pass filter, plus guides that help
> people verify claims themselves.

## Pages
- [Home]({SITE_URL}/): Free spam & fake news checker
- [Blog]({SITE_URL}/blog.html): Guides on spotting fake news and scams
- [About]({SITE_URL}/about.html): What Nofakey.ai is and isn't
- [Contact]({SITE_URL}/contact.html): Get in touch

## Blog posts
{post_lines}
"""
    write(os.path.join(ROOT, "llms.txt"), txt)


# --------------------------------------------------------------------- main

def main():
    posts = collect_posts()
    update_blog_listing(posts)
    update_homepage_preview(posts)
    update_sitemap_xml(posts)
    update_sitemap_html(posts)
    update_rss(posts)
    update_llms_txt(posts)
    print(f"Built site with {len(posts)} blog post(s):")
    for p in posts:
        print(f"  - {p['file']}  ({p['date'][:10]})  {p['title']}")


if __name__ == "__main__":
    main()
    
