import os
import re
from bs4 import BeautifulSoup
from collections import defaultdict
from runtime.locanto_browser_scraper import LISTING_SELECTORS, DETAIL_SELECTORS

dir_path = 'locanto'
fields = {
    'title': [
        'a.posting_listing__title .h3.js-result_title',
        'div.h3.js-result_title',
        'h1.app_title',
        'h1',
        '.vap_header__title',
    ],
    'url': [
        'a.posting_listing__title',
    ],
    'location': [
        'span.js-result_location',
        'span.posting_listing__city',
        'span[itemprop="addressLocality"]',
        '.vap_posting_details__address',
        'div[class*="location"]',
        'span[class*="location"]',
    ],
    'description': [
        'div.posting_listing__description',
        '.js-description_snippet',
        '.vap__description',
        '.vap_user_content__description',
        'div[class*="description"]',
        'div[class*="content"]',
    ],
    'age': [
        'span.posting_listing__age',
        '.header-age',
        '.vap_user_content__feature_value',
        'span[class*="age"]',
    ],
    'category': [
        'span.posting_listing__category a',
    ],
    'images': [
        '.user_images__img',
        'img[src*="locanto"]',
        'img.posting_listing__image',
    ],
    'contact_info': [
        '.vap__description',
        '.contact_buttons__button--call',
        'div[class*="contact"]',
        'div[class*="phone"]',
        'a[href^="tel:"]',
    ],
    'ad_id': [],
}

# Helper to extract with all selectors
def try_selectors(soup, selectors, attr=None):
    for sel in selectors:
        found = soup.select(sel)
        if found:
            if attr:
                vals = [f.get(attr) for f in found if f.get(attr)]
                if vals:
                    return vals
            else:
                vals = [f.get_text(strip=True) for f in found if f.get_text(strip=True)]
                if vals:
                    return vals
    return []

def extract_meta(soup, name):
    tag = soup.find('meta', attrs={'name': name})
    return tag['content'] if tag and tag.has_attr('content') else ''

def extract_og(soup, prop):
    tag = soup.find('meta', attrs={'property': prop})
    return tag['content'] if tag and tag.has_attr('content') else ''

tags_dir = 'tags'
html_files = [f for f in os.listdir(tags_dir) if f.endswith('.html')]

selector_results = defaultdict(lambda: defaultdict(list))  # selector_results[field][selector] = [True/False,...]

print(f"Validating Locanto selectors against {len(html_files)} HTML files in '{tags_dir}'...\n")

for filename in html_files:
    path = os.path.join(tags_dir, filename)
    with open(path, 'r', encoding='utf-8') as f:
        html = f.read()
    soup = BeautifulSoup(html, 'html.parser')
    print(f"File: {filename}")
    # Listing selectors
    for field, selectors in LISTING_SELECTORS.items():
        for sel in selectors:
            found = soup.select(sel)
            ok = bool(found)
            selector_results[f'listing:{field}'][sel].append(ok)
            print(f"  [listing] {field:12} | {sel:60} | {'OK' if ok else 'FAIL'}")
    # Detail selectors
    for field, selectors in DETAIL_SELECTORS.items():
        for sel in selectors:
            found = soup.select(sel)
            ok = bool(found)
            selector_results[f'detail:{field}'][sel].append(ok)
            print(f"  [detail ] {field:12} | {sel:60} | {'OK' if ok else 'FAIL'}")
    print()

# Summary
print("\n=== Selector Summary ===\n")
for field_sel, results in selector_results.items():
    print(f"{field_sel}:")
    for sel, oks in results.items():
        total = len(oks)
        ok_count = sum(oks)
        if ok_count == total:
            status = 'ALWAYS'
        elif ok_count == 0:
            status = 'NEVER'
        else:
            status = f'SOMETIMES ({ok_count}/{total})'
        print(f"  {sel:60} | {status}")
    print()

for fname in os.listdir(dir_path):
    if not fname.endswith('.html'):
        continue
    print(f'\n==== {fname} ===')
    with open(os.path.join(dir_path, fname), encoding='utf-8') as f:
        html = f.read()
    soup = BeautifulSoup(html, 'html.parser')
    report = {}
    # Title
    titles = try_selectors(soup, fields['title'])
    if not titles:
        meta_title = extract_meta(soup, 'dc.title') or extract_og(soup, 'og:title')
        if meta_title:
            titles = [meta_title]
    report['title'] = titles
    # URL (listing page only)
    urls = try_selectors(soup, fields['url'], attr='href')
    report['url'] = urls
    # Location
    locations = try_selectors(soup, fields['location'])
    if not locations:
        meta_loc = extract_meta(soup, 'geo.placename')
        if meta_loc:
            locations = [meta_loc]
    report['location'] = locations
    # Description
    descs = try_selectors(soup, fields['description'])
    if not descs:
        meta_desc = extract_meta(soup, 'description') or extract_meta(soup, 'dc.description')
        if meta_desc:
            descs = [meta_desc]
    report['description'] = descs
    # Age
    ages = try_selectors(soup, fields['age'])
    if not ages:
        # Try to extract from description
        if descs:
            m = re.search(r'(\d{2})\s*years', descs[0])
            if m:
                ages = [m.group(1)]
    report['age'] = ages
    # Category
    cats = try_selectors(soup, fields['category'])
    report['category'] = cats
    # Images
    imgs = try_selectors(soup, fields['images'], attr='src')
    if not imgs:
        og_img = extract_og(soup, 'og:image')
        if og_img:
            imgs = [og_img]
    report['images'] = imgs
    # Contact info
    contacts = try_selectors(soup, fields['contact_info'])
    # Try to extract phone from description
    phone = ''
    if descs:
        m = re.search(r'(\+?\d[\d\s\-]{7,}\d)', descs[0])
        if m:
            phone = m.group(1)
    if phone:
        contacts.append(phone)
    report['contact_info'] = contacts
    # Ad ID
    ad_id = ''
    m = re.search(r'ID_(\d+)', html)
    if m:
        ad_id = m.group(1)
    report['ad_id'] = [ad_id] if ad_id else []
    # Print summary
    for k, v in report.items():
        print(f'{k}: {v[:2]}')
    # Suggest new selectors if missing
    for k, v in report.items():
        if not v:
            print(f'  [!] {k} missing in {fname}')
    print('-----------------------------') 