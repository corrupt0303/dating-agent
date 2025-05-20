import re
from bs4 import BeautifulSoup
from glob import glob

# Define the fields and their current selectors
SELECTORS = {
    'title': [
        'div.h3.js-result_title',
        'h2.listing-title',
        'span.listing-title',
    ],
    'url': [
        'a.posting_listing__title',
    ],
    'location': [
        'span.js-result_location',
        'div.location',
        'span.location',
    ],
    'description': [
        'div.posting_listing__description',
        'div.description',
        'span.description',
    ],
    'age': [
        'span.posting_listing__age',
        'span.age',
    ],
    'category': [
        'span.posting_listing__category a',
        'a.category-link',
    ],
}

# Keywords to help guess new selectors
FIELD_KEYWORDS = {
    'title': ['title', 'headline'],
    'url': ['link', 'url', 'href'],
    'location': ['location', 'city', 'place'],
    'description': ['description', 'desc', 'summary', 'snippet'],
    'age': ['age'],
    'category': ['category', 'cat'],
}

# Helper to flatten selectors for BeautifulSoup
def flatten_selectors(selectors):
    return ', '.join(selectors)

def analyze_html_files():
    html_files = sorted(glob("map_debug_depth*.html"))
    if not html_files:
        print("No map_debug_depth*.html files found. Skipping selector analysis.")
        return
    print(f"Found {len(html_files)} HTML files to analyze.")
    new_selectors = {k: set() for k in SELECTORS}
    coverage_report = {k: 0 for k in SELECTORS}
    total_containers = 0
    for fname in html_files:
        print(f"\nAnalyzing {fname}...")
        with open(fname, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")
        containers = soup.select('article.posting_listing, li.listing, div.listing')
        print(f"  Found {len(containers)} listing containers.")
        total_containers += len(containers)
        for c in containers:
            for field, selectors in SELECTORS.items():
                found = False
                for sel in selectors:
                    if c.select_one(sel):
                        found = True
                        break
                if found:
                    coverage_report[field] += 1
                else:
                    # Try to guess new selectors by looking for tags/classes with field keywords
                    for tag in c.find_all(True):
                        classes = ' '.join(tag.get('class', []))
                        text = tag.get_text(strip=True).lower()
                        for kw in FIELD_KEYWORDS[field]:
                            if kw in classes or kw in text:
                                # Build a selector for this tag
                                tag_selector = tag.name
                                if tag.get('class'):
                                    tag_selector += '.' + '.'.join(tag.get('class'))
                                new_selectors[field].add(tag_selector)
        print(f"  Field coverage so far: {coverage_report}")
    # Suggest new selectors
    print("\nSuggested new selectors:")
    for field, selectors in new_selectors.items():
        if selectors:
            print(f"  {field}: {selectors}")
    # Auto-update locanto_browser_scraper.py
    update_locanto_browser_scraper(new_selectors)
    # Print summary
    print("\nCoverage summary:")
    for field, count in coverage_report.items():
        print(f"  {field}: {count}/{total_containers}")

def update_locanto_browser_scraper(new_selectors):
    """
    Update the SELECTORS in locanto_browser_scraper.py by adding new selectors if not already present.
    """
    scraper_path = 'locanto_browser_scraper.py'
    with open(scraper_path, 'r', encoding='utf-8') as f:
        code = f.read()
    # For each field, add new selectors to the relevant query_selector or query_selector_all calls
    for field, selectors in new_selectors.items():
        if not selectors:
            continue
        # Find the relevant line in the code
        pattern = rf"(await art\.query_selector\(['\"])([^'\"]*)['\"]\) if art else None"  # Only for search_listings
        matches = list(re.finditer(pattern, code))
        for m in matches:
            if field in m.group(2):
                # Already present, skip
                continue
            # Add new selectors to the string
            new_sel_str = m.group(2) + ', ' + ', '.join(selectors)
            code = code.replace(m.group(0), f"await art.query_selector('{new_sel_str}') if art else None")
    # Save the updated code
    with open(scraper_path, 'w', encoding='utf-8') as f:
        f.write(code)
    print("\nlocanto_browser_scraper.py updated with new selectors (if any were found).")

if __name__ == "__main__":
    import os
    import re
    from bs4 import BeautifulSoup

    locanto_dir = "locanto"
    html_files = glob(os.path.join(locanto_dir, "*.html"))
    location_slugs = set()
    category_slugs = set()
    section_ids = set()
    all_urls = set()

    url_pattern = re.compile(r"https://www\.locanto\.co\.za/([a-zA-Z0-9\-]+)/([a-zA-Z0-9\-]+)/([a-zA-Z0-9]+)/")
    # Also match /g/q/?query=...
    gq_pattern = re.compile(r"https://www\.locanto\.co\.za/g/q/\?query=")
    # Also match /<location>/ only
    location_only_pattern = re.compile(r"https://www\.locanto\.co\.za/([a-zA-Z0-9\-]+)/")

    for html_file in html_files:
        with open(html_file, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("https://www.locanto.co.za/"):
                    all_urls.add(href)
                    m = url_pattern.match(href)
                    if m:
                        location_slugs.add(m.group(1))
                        category_slugs.add(m.group(2))
                        section_ids.add(m.group(3))
                    elif gq_pattern.match(href):
                        category_slugs.add("g/q")
                    else:
                        m2 = location_only_pattern.match(href)
                        if m2:
                            location_slugs.add(m2.group(1))

    print("# Unique Locanto location slugs:")
    print(sorted(location_slugs))
    print("\n# Unique Locanto category slugs:")
    print(sorted(category_slugs))
    print("\n# Unique Locanto section/category IDs:")
    print(sorted(section_ids))
    print("\n# Example URLs found:")
    for url in sorted(list(all_urls))[:20]:
        print(url)
    print(f"\nTotal URLs found: {len(all_urls)}")

    analyze_html_files() 