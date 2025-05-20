import os
import re
import urllib.parse
from bs4 import BeautifulSoup

TAGS_DIR = "tags"

category_slugs = set()
section_ids = set()
tag_slugs = set()

def extract_from_url(url):
    # Unwrap proxy if present
    if url.startswith("https://please.untaint.us?url="):
        url = urllib.parse.unquote(url.split("url=", 1)[1])
    # /g/<Category-Slug>/<Section-ID>/
    m = re.match(r"https://www\.locanto\.co\.za/g/([^/]+)/([^/]+)/", url)
    if m:
        category_slugs.add(m.group(1))
        section_ids.add(m.group(2))
    # /g/tag/<tag>/
    m2 = re.match(r"https://www\.locanto\.co\.za/g/tag/([^/]+)/", url)
    if m2:
        tag_slugs.add(m2.group(1))

# Parse all .html files in tags/
for fname in os.listdir(TAGS_DIR):
    if not fname.endswith(".html"):
        continue
    with open(os.path.join(TAGS_DIR, fname), encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")
        for a in soup.find_all("a", href=True):
            extract_from_url(a["href"])

# Also parse tags/latest.txt if it exists
latest_path = os.path.join(TAGS_DIR, "latest.txt")
if os.path.exists(latest_path):
    with open(latest_path, encoding="utf-8") as f:
        text = f.read()
        # Try to extract all hrefs from the file
        for url in re.findall(r'href=["\']([^"\']+)["\']', text):
            extract_from_url(url)
        # Also try to extract all URLs directly (for robustness)
        for url in re.findall(r'https://www\.locanto\.co\.za/[^\s"\'>]+', text):
            extract_from_url(url)

print("\n# LOCANTO_CATEGORY_SLUGS = set([")
for slug in sorted(category_slugs):
    print(f"    '{slug}',")
print("])")

print("\n# LOCANTO_SECTION_IDS = set([")
for sid in sorted(section_ids):
    print(f"    '{sid}',")
print("])")

print("\n# LOCANTO_TAG_SLUGS = set([")
for tag in sorted(tag_slugs):
    print(f"    '{tag}',")
print("])") 