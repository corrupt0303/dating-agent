import re
from pathlib import Path

HTML_PATH = Path('locations/list.html')
CONSTANTS_PATH = Path('locanto_constants.py')

# 1. Extract all location slugs from the HTML
with HTML_PATH.open(encoding='utf-8') as f:
    html = f.read()

# Regex to match slugs in hrefs like https://www.locanto.co.za/<slug>/
slugs = set(
    m.group(1).lower()
    for m in re.finditer(r'href="https://www\.locanto\.co\.za/([a-z0-9-]+)/"', html)
)
slugs = sorted(slugs)

# 2. Read the constants file
with CONSTANTS_PATH.open(encoding='utf-8') as f:
    code = f.read()

# 3. Replace the LOCANTO_LOCATION_SLUGS set
pattern = re.compile(
    r'(LOCANTO_LOCATION_SLUGS\s*=\s*set\(\[)(.*?)(\]\))',
    re.DOTALL
)

new_set = 'LOCANTO_LOCATION_SLUGS = set([\n' + ''.join(f"    '{slug}',\n" for slug in slugs) + '])'

# Replace the old set with the new one
new_code = pattern.sub(new_set, code, count=1)

# 4. Write back the updated file
with CONSTANTS_PATH.open('w', encoding='utf-8') as f:
    f.write(new_code)

print(f"Updated LOCANTO_LOCATION_SLUGS with {len(slugs)} locations.") 