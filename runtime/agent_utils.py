import asyncio
import re
from difflib import get_close_matches
from typing import Dict, Any

# Import the lists from dating.py
from .locanto_constants import LOCANTO_CATEGORY_SLUGS, LOCANTO_LOCATION_SLUGS, LOCANTO_SECTION_IDS, LOCANTO_TAG_SLUGS

# --- Locanto valid slugs and mapping (auto-generated) ---
LOCANTO_CATEGORY_SLUGS = set([
    'Accessories-Jewellery',
    'Accountant',
    'Accounting-Financing-Banking',
    'Activity-Partners',
    'Administrative-Support',
    'Art-Music-Dance-Classes',
    'Artists',
    'Arts-Antiques',
    'Arts-Crafts',
    'Arts-Culture',
    'Audio-Headphones',
    'BDSM-Fetish',
    'BPO-KPO',
    'Baby-Kids',
    'Baby-Kids-Clothes',
    'Babysitter',
    'Bangles-Bracelets',
    'Bars-Clubs',
    'Bathroom',
    'Bedroom',
    'Bicycles',
    'Boats',
    'Books',
    'Buggies-Pushchairs',
    'CDs-Records',
    'Cameras-Accessories',
    'Car-Services',
    'Caravans-Motorhomes',
    'Carriers-Child-Seats',
    'Cars',
    'Casual-Encounters',
    'Children-s-Furniture',
    'Classes',
    'Cleaning-Services',
    'Collectables',
    'Community',
    'Computer-Classes',
    'Computer-Tech-Help',
    'Computers-Software-Components',
    'Concerts',
    'Construction-Manufacturing',
    'Construction-Materials',
    'Construction-Services',
    'Continuing-Education',
    'Controller',
    'Costumes',
    'Couples-Seeking-Couples',
    'Couples-Seeking-Men',
    'Couples-Seeking-Women',
    'Cultural-Events',
    'DIY-Tools-Home-Improvement',
    'Design-Architecture',
    'Dining-Room',
    'Drones',
    'Earrings-Rings',
    'Education-Training',
    'Elderly-Home-Assistance',
    'Engineering',
    'Equipment-for-Businesses',
    'Erotic-Photographers-Models',
    'Estate-Agents-Property-Brokers',
    'Events',
    'Exotic-Dancers',
    'Fan-Pages',
    'Fashion-Accessories',
    'Fashion-Beauty',
    'Fetish-Encounters',
    'Finance',
    'Flatmates',
    'Flats-for-Rent',
    'For-Sale',
    'Government-Public-Service',
    'Health-Beauty-Products',
    'Healthcare',
    'Healthcare-Lab-Dental',
    'Heavy-Machinery',
    'Hobby-Leisure',
    'Home-Appliances',
    'Home-Garden',
    'Hospitality-Tourism-Travel',
    'Household-Help',
    'Houses-for-Rent',
    'Industrial',
    'Information-Technology',
    'Insurance',
    'Internships',
    'Investment-Banker',
    'Investment-Broker',
    'Jobs',
    'Labour',
    'Language-Classes',
    'Legal-Consulting',
    'Light-Machinery',
    'Living-Room',
    'Long-Term-Relationships',
    'Lost-Found',
    'M4w',
    'Marketing-Advertising-PR',
    'Massages',
    'Men-Looking-for-Men',
    'Men-Looking-for-Women',
    'Men-Seeking-Men',
    'Men-Seeking-Women',
    'Men-s-Clothes',
    'Metalworking-Manufacturing',
    'Missed-Connections',
    'Movies-Blu-rays-DVDs',
    'Multi-Level-Marketing',
    'Multimedia-Electronics',
    'Music-Movies-Books',
    'Musical-Instruments',
    'Musicians-Bands',
    'Office-Supplies-Stationery',
    'Other-Classes',
    'Other-Events',
    'Other-Hobbies',
    'Other-Jobs',
    'Other-Personals-Services',
    'Part-Time-Jobs-Side-Jobs',
    'Personals',
    'Personals-Services',
    'Pet-Sitting',
    'Pet-Supplies',
    'Phone-Cam',
    'Phones-Mobiles-Accessories',
    'Property',
    'Recruitment-HR',
    'Recruitment-HR-Services',
    'Retail-Food-Wholesale',
    'Rideshare-Carpool',
    'Rooms-for-Rent',
    'Sales-Distribution',
    'Service',
    'Services',
    'Shopping',
    'Skills-Language-Swap',
    'Smartwatches',
    'Social-Work-Nonprofit',
    'Sporting-Events',
    'Sports-Outdoors',
    'Sports-Wellness-Classes',
    'T4m',
    'TS-for-Men',
    'Technician-Jobs',
    'Theatre-Comedy-Shows',
    'Toys-Games',
    'Traineeships',
    'Transportation-Logistics',
    'Tutoring-Learning-Centres',
    'Vehicles',
    'Virtual-Adventures',
    'W4m',
    'Watches',
    'Women-Looking-for-Men',
    'Women-Looking-for-Women',
    'Women-Seeking-Men',
    'Women-Seeking-Women',
    'Women-s-Clothes',
    'dol',
    'info',
    'premium',
    'run',
    'tag',
])
LOCANTO_SECTION_IDS = set([
    '101',
    '102',
    '104',
    '105',
    '106',
    '108',
    '110',
    '112',
    '116',
    '120',
    '201',
    '202',
    '203',
    '204',
    '206',
    '207',
    '20701',
    '20702',
    '20703',
    '20704',
    '20705',
    '20707',
    '20708',
    '20709',
    '20711',
    '20713',
    '209',
    '20901',
    '20903',
    '20905',
    '20907',
    '20950',
    '20952',
    '20954',
    '20956',
    '20958',
    '20960',
    '20962',
    '20964',
    '20970',
    '211',
    '301',
    '302',
    '304',
    '307',
    '403',
    '406',
    '407',
    '408',
    '411',
    '412',
    '413',
    '414',
    '415',
    '416',
    '417',
    '418',
    '419',
    '420',
    '42003',
    '42005',
    '42008',
    '42010',
    '424',
    '425',
    '426',
    '427',
    '430',
    '431',
    '444',
    '445',
    '448',
    '449',
    '454',
    '455',
    '460',
    '462',
    '468',
    '470',
    '471',
    '479',
    '481',
    '504',
    '505',
    '516',
    '520',
    '523',
    '524',
    '601',
    '602',
    '605',
    '60503',
    '60505',
    '60509',
    '60511',
    '606',
    '607',
    '608',
    '609',
    '611',
    '61101',
    '61111',
    '612',
    '613',
    '614',
    '615',
    '616',
    '617',
    '618',
    '620',
    '622',
    '623',
    '624',
    '626',
    '628',
    '630',
    '632',
    '636',
    '638',
    '642',
    '644',
    '646',
    '701',
    '703',
    '707',
    '709',
    '711',
    '713',
    '751',
    '753',
    '755',
    '757',
    '761',
    '802',
    '803',
    '804',
    '805',
    '806',
    '807',
    '901',
    '902',
    '905',
    '910',
    'Aerobics',
    'B',
    'BDSM',
    'Bags-and-Handbags',
    'Banker',
    'Banking',
    'C',
    'Crossdresser',
    'Diamonds',
    'E',
    'F',
    'Female-Singer',
    'Fetish',
    'FinDom',
    'Foot-Fetish',
    'G',
    'Grader',
    'H',
    'Happy-Ending-Massage',
    'I',
    'J',
    'Jewellery',
    'K',
    'L',
    'Loader',
    'M',
    'MILF',
    'N',
    'Necklaces-Pendants',
    'P',
    'Party-DJ',
    'Phone-Sex',
    'Pianist',
    'R',
    'Risk-Manager',
    'S',
    'T',
    'Threesome',
    'Transsexuals',
    'accessibility',
    'au-pairs',
    'babysitters',
    'bi-male',
    'blowjob',
    'body-to-body-massage',
    'businesses',
    'caretaker',
    'cart',
    'child-care',
    'couple-swapping',
    'faq',
    'faq_contact',
    'femdom',
    'gardeners',
    'gay',
    'guitarists',
    'hook-ups',
    'hot-girls',
    'international',
    'lesbians',
    'male-singer',
    'man-needed',
    'nannies',
    'one-night-stand',
    'quickie',
    'rock-singers',
    'sex',
    'threesome-couple',
    'transgender',
    'worship',
])
LOCANTO_TAG_SLUGS = set([
    'Aerobics',
    'BDSM',
    'Bags-and-Handbags',
    'Banker',
    'Banking',
    'Crossdresser',
    'Diamonds',
    'Female-Singer',
    'Fetish',
    'FinDom',
    'Foot-Fetish',
    'Grader',
    'Happy-Ending-Massage',
    'Jewellery',
    'Loader',
    'MILF',
    'Necklaces-Pendants',
    'Party-DJ',
    'Phone-Sex',
    'Pianist',
    'Risk-Manager',
    'Threesome',
    'Transsexuals',
    'au-pairs',
    'babysitters',
    'bi-male',
    'blowjob',
    'body-to-body-massage',
    'caretaker',
    'child-care',
    'couple-swapping',
    'femdom',
    'gardeners',
    'gay',
    'guitarists',
    'hook-ups',
    'hot-girls',
    'lesbians',
    'male-singer',
    'man-needed',
    'nannies',
    'one-night-stand',
    'quickie',
    'rock-singers',
    'sex',
    'threesome-couple',
    'transgender',
    'worship',
])

def chunk_text(text, chunk_size=2000):
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

async def speak_chunks(session, text, max_auto_chunks=3, pause=1.0):
    """Speak all chunks of text, auto-continue up to max_auto_chunks, then prompt for 'more'."""
    chunks = chunk_text(text)
    for i, chunk in enumerate(chunks):
        await session.generate_reply(instructions=chunk)
        if i < len(chunks) - 1:
            if i + 1 >= max_auto_chunks:
                await session.generate_reply(instructions="There is more information. Say 'more' to continue.")
                break
            await asyncio.sleep(pause)

def construct_locanto_query(user_input: str) -> Dict[str, Any]:
    """
    Parse user input and return a dict of valid Locanto search parameters.
    Uses fuzzy matching for category, location, section, and tag.
    """
    text = user_input.lower()
    params = {}

    # Extract location (fuzzy match against known slugs)
    loc_match = None
    for word in text.split():
        loc = get_close_matches(word.replace(' ', '-'), LOCANTO_LOCATION_SLUGS, n=1, cutoff=0.8)
        if loc:
            params['location'] = loc[0]
            loc_match = loc[0]
            break
    # If not found, try multi-word locations
    if 'location' not in params:
        for loc_slug in LOCANTO_LOCATION_SLUGS:
            if loc_slug.replace('-', ' ') in text or loc_slug in text:
                params['location'] = loc_slug
                loc_match = loc_slug
                break

    # Extract age range (e.g., 30-40, 30 to 40, between 30 and 40)
    age_min, age_max = None, None
    age_patterns = [
        r'(\d{2})\s*[-to]+\s*(\d{2})',
        r'between\s+(\d{2})\s*(?:and|-)\s*(\d{2})',
        r'ages?\s*(\d{2})\s*[-to]+\s*(\d{2})',
    ]
    for pat in age_patterns:
        m = re.search(pat, text)
        if m:
            age_min, age_max = int(m.group(1)), int(m.group(2))
            break
    if age_min:
        params['age_min'] = age_min
    if age_max:
        params['age_max'] = age_max

    # Extract category (fuzzy match)
    cat_match = None
    for word in text.split():
        cat = get_close_matches(word.replace(' ', '-').title(), LOCANTO_CATEGORY_SLUGS, n=1, cutoff=0.7)
        if cat:
            params['category'] = cat[0]
            cat_match = cat[0]
            break
    # Try multi-word categories
    if 'category' not in params:
        for cat_slug in LOCANTO_CATEGORY_SLUGS:
            if cat_slug.replace('-', ' ').lower() in text or cat_slug.lower() in text:
                params['category'] = cat_slug
                cat_match = cat_slug
                break

    # Extract section (fuzzy match)
    sec_match = None
    for word in text.split():
        sec = get_close_matches(word, LOCANTO_SECTION_IDS, n=1, cutoff=0.8)
        if sec:
            params['section'] = sec[0]
            sec_match = sec[0]
            break

    # Extract tag (fuzzy match against LOCANTO_TAG_SLUGS)
    tag_match = None
    for word in text.split():
        tag = get_close_matches(word.replace(' ', '-').lower(), LOCANTO_TAG_SLUGS, n=1, cutoff=0.7)
        if tag:
            params['tag'] = tag[0]
            tag_match = tag[0]
            break
    # Try multi-word tags
    if 'tag' not in params:
        for tag_slug in LOCANTO_TAG_SLUGS:
            if tag_slug.replace('-', ' ') in text or tag_slug in text:
                params['tag'] = tag_slug
                tag_match = tag_slug
                break

    # If still no tag, use the first non-matched word as tag if not a stopword
    stopwords = set(['in', 'between', 'and', 'to', 'for', 'with', 'of', 'the', 'a', 'an', 'on', 'at', 'by'])
    tag_candidates = [w for w in text.split() if w not in stopwords]
    for w in tag_candidates:
        if w not in (loc_match, cat_match, sec_match, tag_match):
            params['tag'] = w
            break

    # Default query: use the whole input
    params['query'] = user_input.strip()

    return params

# Optionally, expose as a function tool for the agent
try:
    from livekit.agents import function_tool, RunContext
    import json

    @function_tool
    async def construct_locanto_query_tool(context: RunContext, user_input: str) -> str:
        params = construct_locanto_query(user_input)
        return json.dumps(params)
except ImportError:
    pass

def sanitize_stt_input(text: str) -> str:
    """Remove standalone trigger words from STT input."""
    # Remove 'cs go', 'cortana', and 'play' as standalone words (case-insensitive)
    pattern = r'\b(cs go|cortana|play)\b'
    sanitized = re.sub(pattern, '', text, flags=re.IGNORECASE)
    # Remove extra spaces
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    return sanitized 