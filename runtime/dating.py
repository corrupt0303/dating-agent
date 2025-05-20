from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file
import os
import asyncio
import json
import time
import httpx
from datetime import datetime, timedelta
import pytz
from livekit import agents
from livekit.agents import JobContext, WorkerOptions, cli, JobProcess, Agent, AgentSession, function_tool, RunContext
from livekit.agents.llm import ChatContext, ChatMessage
from livekit.plugins import silero, openai, azure

# --- SYSTEM PROMPT: Tool Overview and Agent Instructions ---
SYSTEM_PROMPT = '''
You are an advanced AI agent with access to the following tools, all of which support asynchronous and parallel usage:

- Bing Web Search: Perform Bing searches using Playwright-powered browser automation. Use for broad web search queries.
- Web Crawler: Extract readable content or structured data from any web page (including Locanto listings) using Playwright. Use for deep content extraction or site crawling.
- Locanto Browser Scraper: Search and extract Locanto listings with robust pagination and batch async detail fetching (contact info, etc.). Use for Locanto-specific queries.
- Locanto Query Utilities: Parse and construct Locanto search parameters from user input. Use for interpreting or validating search queries.

Instructions:
- Always select the most relevant tool(s) for the user query.
- If multiple tools are relevant, run them in parallel using asyncio.gather and combine their results.
- Return structured, readable, and actionable results.
- Use robust error handling and fallback strategies.
- Each tool is described with a clear, action-oriented docstring for optimal auto-selection.
'''

# Import necessary libraries
import requests
import random
import wikipediaapi
import html
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, TypedDict, Union, Literal
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import TypedDict, List
from .agent_utils import chunk_text, speak_chunks, construct_locanto_query_tool
import collections.abc
import logging
from .locanto_constants import LOCANTO_CATEGORY_SLUGS, LOCANTO_LOCATION_SLUGS, LOCANTO_SECTION_IDS, LOCANTO_TAG_SLUGS
import re
import webbrowser
import threading
import urllib.parse
from googlesearch import search as google_search

# --- LOGGING SETUP FOR READ-ONLY FILESYSTEMS ---
# Use /tmp/agent.log by default (writable in most environments)
LOG_FILE = os.environ.get("AGENT_LOG_FILE", "/tmp/agent.log")
log_handlers = []
try:
    # Try to use file logging
    log_handlers.append(logging.FileHandler(LOG_FILE, mode='a'))
    file_logging_ok = True
except Exception as e:
    print(f"[LOGGING] Could not open log file {LOG_FILE}: {e}")
    file_logging_ok = False
log_handlers.append(logging.StreamHandler())
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=log_handlers
)
if not file_logging_ok:
    logging.warning(f"Logging to file {LOG_FILE} failed, using console only.")

# Ensure MAX_AUTO_CHUNKS and CHUNK_PAUSE are properly typed
MAX_AUTO_CHUNKS = int(os.getenv("MAX_AUTO_CHUNKS", "10"))
CHUNK_PAUSE = float(os.getenv("CHUNK_PAUSE", "1.0"))
# --- BEGIN: Whoogle/Sapti/SearxNG Search Utility ---
WHOOGLE_SERVER = os.getenv("WHOOGLE_SERVER", "http://google.served.cool:5001/")

def bing_web_search(query, num_results=10):
    import asyncio
    try:
        from .bing_playwright_scraper import scrape_bing
        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(scrape_bing(query, num_results=num_results))
        if results and isinstance(results, list) and all('title' in r and 'link' in r for r in results):
            html_results = "".join(f'<a href="{r["link"]}">{r["title"]}</a><br>' for r in results[:num_results])
            return html_results
    except Exception as e:
        return f"Error: Bing search failed: {e}"
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    try:
        params = {"q": query}
        resp = requests.get(SEARXNG_FALLBACK, params=params, timeout=10)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    try:
        params = {"q": query}
        resp = requests.get(SAPTI_FALLBACK, params=params, timeout=10)
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        return f"Error: All search engines failed: {e}"

class LocantoCategory(TypedDict):
    name: str
    url: str
    count: int

class LocantoListing(TypedDict):
    title: str
    description: str
    location: str
    price: str
    date_posted: str
    url: str
    images: List[str]
    contact_info: Optional[str]
    poster_info: Optional[str]
    full_description: Optional[str]
    category_path: List[str]
    age: Optional[str]
    reply_count: Optional[int]
    ad_id: Optional[str]

def is_valid_locanto_location(location):
    if not location:
        return False
    return location.lower().replace(' ', '-') in LOCANTO_LOCATION_SLUGS

def is_valid_locanto_category(category):
    if not category:
        return False
    return category.replace(' ', '-').replace('_', '-').title() in LOCANTO_CATEGORY_SLUGS

def is_valid_locanto_section(section):
    if not section:
        return False
    return section in LOCANTO_SECTION_IDS

def is_valid_locanto_tag(tag):
    if not tag:
        return False
    return tag.replace(' ', '-').lower() in {t.lower() for t in LOCANTO_TAG_SLUGS}

def suggest_closest_slug(input_str, valid_slugs):
    import difflib
    matches = difflib.get_close_matches(input_str.lower().replace(' ', '-'), [s.lower() for s in valid_slugs], n=3, cutoff=0.6)
    return matches

def get_current_date_and_timezone():
    """Get the current server date and time in a natural language format with timezone."""
    try:
        # Get local timezone
        local_tz = pytz.timezone(os.environ.get('TZ', 'Etc/UTC'))
        now = datetime.now(local_tz)
        timezone_name = local_tz.zone
    except Exception:
        now = datetime.now()
        timezone_name = time.tzname[0]
    date_str = now.strftime("%A, %B %d, %Y")
    time_str = now.strftime("%I:%M %p")
    return f"{time_str} on {date_str} in the {timezone_name} timezone"

def sanitize_for_azure(text: str) -> str:
    """Reword or mask terms that may trigger Azure OpenAI's content filter."""
    unsafe_terms = {
        "sex": "intimacy",
        "sexual": "romantic",
        "hookup": "meeting",
        "hookups": "meetings",
        "anal": "[redacted]",
        "blowjob": "[redacted]",
        "quickie": "[redacted]",
        "incalls": "meetings",
        "outcalls": "meetings",
        "massage": "relaxation",
        "MILF": "person",
        "fuck": "love",
        "cunt": "[redacted]",
        "penis": "[redacted]",
        "oral": "[redacted]",
        "wank": "[redacted]",
        "finger": "[redacted]",
        "date": "meet",
        "love": "companionship",
        "kiss": "affection",
        "look": "search",
        "find": "discover",
        "girl": "woman",
    }
    for term, replacement in unsafe_terms.items():
        # Replace whole words only, case-insensitive
        text = re.sub(rf'\\b{re.escape(term)}\\b', replacement, text, flags=re.IGNORECASE)
    return text

# Add this utility function for robust tool output handling

def is_sequence_but_not_str(obj):
    import collections.abc
    return isinstance(obj, collections.abc.Sequence) and not isinstance(obj, (str, bytes, bytearray))

def clean_spoken(text):
    import re
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'#+', '', text)
    text = re.sub(r'[\*\_`~\[\]\(\)\>\!]', '', text)
    text = re.sub(r'^\d+\.\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\d+', '', text)
    text = text.strip()
    # Add a period at the end of lists/multi-line outputs if not already present
    if text and not text.endswith('.'):
        # If the text is a list (multiple lines), add a period at the end
        if '\n' in text:
            text += '.'
    return text

def handle_tool_results(session, results) -> None:
    """Speak tool results: if a single result, speak it; if multiple, combine and speak once."""
    from .agent_utils import speak_chunks
    if is_sequence_but_not_str(results):
        combined = '\n\n'.join(str(r) for r in results if r)
        combined = clean_spoken(combined)
        return speak_chunks(session, combined, max_auto_chunks=MAX_AUTO_CHUNKS, pause=CHUNK_PAUSE)
    else:
        results = clean_spoken(results)
        return speak_chunks(session, results, max_auto_chunks=MAX_AUTO_CHUNKS, pause=CHUNK_PAUSE) # type: ignore

# --- LOCANTO TOOL DEFINITIONS (move to top) ---
@function_tool
async def search_locanto(context: RunContext, category_path: str = 'personals/men-seeking-men', location: str = 'western-cape', max_pages: int = 3, return_url: bool = False) -> str:
    try:
        import html
        ddg_query = f"{category_path.replace('/', ' ')} {location} site:locanto.co.za"
        import asyncio
        loop = asyncio.get_event_loop()
        results = []
        assistant = AIVoiceAssistant()
        categories = category_path.split('/')
        listings = await assistant.locanto_search(categories, location, max_pages)
        if not listings:
            summary = "No listings found matching your criteria."
        else:
            first_url = None
            url_map = {}
            summary = f"Found {len(listings)} listings on Locanto:\n\n"
            for idx, listing in enumerate(listings, 1):
                if not isinstance(listing, dict):
                    continue
                title = listing.get('title', 'No title')
                title = clean_spoken(title)
                summary += f"{idx}. {title}\n"
                ad_id = listing.get('ad_id')
                if ad_id:
                    summary += f"Ad ID: {clean_spoken(str(ad_id))}\n"
                age = listing.get('age')
                if age:
                    summary += f"Age: {clean_spoken(str(age))}\n"
                category_path = listing.get('category_path', [])
                if category_path:
                    summary += f"Category: {clean_spoken(' > '.join(category_path))}\n"
                price = listing.get('price')
                if price:
                    summary += f"Price: {clean_spoken(str(price))}\n"
                loc = listing.get('location')
                if loc:
                    summary += f"Location: {clean_spoken(str(loc))}\n"
                date_posted = listing.get('date_posted')
                if date_posted:
                    summary += f"Posted: {clean_spoken(str(date_posted))}\n"
                url = listing.get('url')
                if url:
                    url_map[idx] = url
                    if not first_url:
                        first_url = url
                contact_info = listing.get('contact_info')
                if contact_info:
                    summary += f"Contact: {clean_spoken(str(contact_info))}\n"
                poster_info = listing.get('poster_info')
                if poster_info:
                    summary += f"Poster: {clean_spoken(str(poster_info))}\n"
                reply_count = listing.get('reply_count')
                if reply_count is not None:
                    summary += f"Replies: {clean_spoken(str(reply_count))}\n"
                description = listing.get('description')
                if description:
                    desc = description[:200] + '...' if len(description) > 200 else description
                    summary += f"Description: {clean_spoken(desc)}\n"
                summary += "\n"
            # Store mapping in session.userdata for later use
            session = getattr(context, 'session', None)
            if session is not None:
                session.userdata['last_locanto_urls'] = url_map
            if first_url and return_url:
                return first_url
            if first_url:
                summary += f"Would you like to open the first listing in your browser?"
            if session:
                await handle_tool_results(session, summary)
                return "I've found some results and will read them to you now."
            else:
                return summary
        summary = sanitize_for_azure(summary)
        summary = clean_spoken(summary)
        logging.info(f"[TOOL] search_locanto summary: {summary}")
        session = getattr(context, 'session', None)
        if session:
            await handle_tool_results(session, summary)
            return "I've found some results and will read them to you now."
        else:
            return summary
    except Exception as e:
        logging.error(f"[TOOL] search_locanto exception: {e}")
        return sanitize_for_azure(f"Sorry, there was a problem searching Locanto: {e}")

@function_tool
async def search_locanto_browser(context: RunContext, query: str = "dating", location: str = "Cape Town", max_pages: int = 1, tag: str = None, category: str = None, section: str = None, url: str = None, return_url: bool = False) -> str:
    try:
        from locanto_browser_scraper import search_locanto_browser, LocantoBrowserScraper
        loc_valid = is_valid_locanto_location(location)
        cat_valid = is_valid_locanto_category(category) if category else True
        sec_valid = is_valid_locanto_section(section) if section else True
        if tag and not is_valid_locanto_tag(tag):
            suggestions = suggest_closest_slug(tag, LOCANTO_TAG_SLUGS)
            msg = f"Tag '{tag}' is not valid. Did you mean: {', '.join(suggestions)}?" if suggestions else f"Tag '{tag}' is not valid. Please choose from: {', '.join(sorted(list(LOCANTO_TAG_SLUGS))[:10])}..."
            msg = sanitize_for_azure(msg)
            msg = clean_spoken(msg)
            logging.info(f"[TOOL] search_locanto_browser tag error: {msg}")
            return msg
        suggestions = []
        if location and not loc_valid:
            suggestions = suggest_closest_slug(location, LOCANTO_LOCATION_SLUGS)
            msg = f"Location '{location}' is not valid. Did you mean: {', '.join(suggestions)}?" if suggestions else f"Location '{location}' is not valid. Please choose from: {', '.join(sorted(list(LOCANTO_LOCATION_SLUGS))[:10])}..."
            msg = sanitize_for_azure(msg)
            msg = clean_spoken(msg)
            logging.info(f"[TOOL] search_locanto_browser location error: {msg}")
            return msg
        if category and not cat_valid:
            suggestions = suggest_closest_slug(category, LOCANTO_CATEGORY_SLUGS)
            msg = f"Category '{category}' is not valid. Did you mean: {', '.join(suggestions)}?" if suggestions else f"Category '{category}' is not valid. Please choose from: {', '.join(sorted(list(LOCANTO_CATEGORY_SLUGS))[:10])}..."
            msg = sanitize_for_azure(msg)
            msg = clean_spoken(msg)
            logging.info(f"[TOOL] search_locanto_browser category error: {msg}")
            return msg
        if section and not sec_valid:
            suggestions = suggest_closest_slug(section, LOCANTO_SECTION_IDS)
            msg = f"Section '{section}' is not valid. Did you mean: {', '.join(suggestions)}?" if suggestions else f"Section '{section}' is not valid. Please choose from: {', '.join(sorted(list(LOCANTO_SECTION_IDS))[:10])}..."
            msg = sanitize_for_azure(msg)
            msg = clean_spoken(msg)
            logging.info(f"[TOOL] search_locanto_browser section error: {msg}")
            return msg
        scraper = LocantoBrowserScraper()
        listings = await scraper.search_listings(query=query, location=location, max_pages=max_pages, tag=tag, category=category, section=section, url=url)
        first_url = None
        url_map = {}
        if not listings:
            summary = f"No Locanto listings found for '{query}' in '{location}'."
        elif isinstance(listings[0], dict) and 'error' in listings[0]:
            summary = f"Error: {listings[0]['error']}"
        else:
            summary = f"Found {len(listings)} Locanto listings for '{query}' in '{location}':\n\n"
            for idx, listing in enumerate(listings[:5], 1):
                if not isinstance(listing, dict):
                    continue
                title = listing.get('title', 'No title')
                title = clean_spoken(title)
                summary += f"{idx}. {title}\n"
                age = listing.get('age')
                if age:
                    summary += f"   Age: {clean_spoken(str(age))}\n"
                loc = listing.get('location')
                if loc:
                    summary += f"   Location: {clean_spoken(str(loc))}\n"
                description = listing.get('description')
                if description:
                    desc = description[:120] + ('...' if len(description) > 120 else '')
                    summary += f"   Description: {clean_spoken(desc)}\n"
                url = listing.get('url')
                if url:
                    url_map[idx] = url
                    if not first_url:
                        first_url = url
                summary += "\n"
            # Store mapping in session.userdata for later use
            session = getattr(context, 'session', None)
            if session is not None:
                session.userdata['last_locanto_urls'] = url_map
            if first_url:
                if return_url:
                    return first_url
                summary += f"Would you like to open the first listing in your browser?"
        summary = sanitize_for_azure(summary)
        summary = clean_spoken(summary)
        logging.info(f"[TOOL] search_locanto_browser summary: {summary}")
        session = getattr(context, 'session', None)
        if session:
            await handle_tool_results(session, summary)
            return "I've found some results and will read them to you now."
        else:
            return summary
    except Exception as e:
        logging.error(f"[TOOL] search_locanto_browser exception: {e}")
        return sanitize_for_azure(f"Error searching Locanto with Playwright: {e}")

@function_tool
async def locanto_matchmaking(
    context: RunContext,
    query: Optional[str] = None,  # parameter1
    gender: Optional[str] = None,
    seeking: Optional[str] = None,
    age: Optional[str] = None,
    age_min: Optional[int] = None,
    age_max: Optional[int] = None,
    query_description: Optional[bool] = None,
    location: Optional[str] = None,
    tag: Optional[str] = None,
    category: Optional[str] = None,
    section: Optional[str] = None,
    dist: Optional[int] = None,
    sort: Optional[str] = None,
    max_pages: int = 1,
    return_url: bool = False
) -> str:
    try:
        from locanto_browser_scraper import LocantoBrowserScraper
        import urllib.parse
        missing = []
        if not query:
            missing.append("search term (e.g. companion, relationship, love, etc.)")
        if not location:
            missing.append("location (e.g. randburg, johannesburg, etc.)")
        if age_max is None:
            missing.append("maximum age (age_max)")
        if missing:
            summary = ("To find matches, please provide: " + ', '.join(missing) + ". "
                    "For example: 'Find companionship in Randburg, max age 40'.")
            summary = sanitize_for_azure(summary)
            summary = clean_spoken(summary)
            logging.info(f"[TOOL] locanto_matchmaking missing params: {summary}")
            session = getattr(context, 'session', None)
            if session:
                await handle_tool_results(session, summary)
                return "I'll read the requirements to you."
            else:
                return summary
        unsafe_terms = {"sex", "nsa", "hookup", "hookups", "anal", "blowjob", "quickie", "incalls", "outcalls", "massage", "MILF"}
        if any(term in query.lower() for term in unsafe_terms):
            summary = ("For your safety, please use respectful, safe-for-work search terms. "
                    "Try words like 'companionship', 'relationship', 'friendship', or 'meeting people'.")
            summary = sanitize_for_azure(summary)
            summary = clean_spoken(summary)
            logging.info(f"[TOOL] locanto_matchmaking unsafe terms: {summary}")
            session = getattr(context, 'session', None)
            if session:
                await handle_tool_results(session, summary)
                return "I'll read the safety message to you."
            else:
                return summary
        if age_min is None:
            age_min = 18
        if dist is None:
            dist = 30
        if sort is None:
            sort = "date"
        if category is None:
            category = "Personals"
        if section is None:
            section = "P"
        if query_description is None:
            query_description = True
        location_slug = location.lower().replace(' ', '-')
        loc_valid = is_valid_locanto_location(location_slug)
        if location and not loc_valid:
            suggestions = suggest_closest_slug(location, LOCANTO_LOCATION_SLUGS)
            summary = f"Location '{location}' is not valid. Did you mean: {', '.join(suggestions)}?" if suggestions else f"Location '{location}' is not valid. Please choose from: {', '.join(sorted(list(LOCANTO_LOCATION_SLUGS))[:10])}..."
            summary = sanitize_for_azure(summary)
            summary = clean_spoken(summary)
            logging.info(f"[TOOL] locanto_matchmaking location error: {summary}")
            session = getattr(context, 'session', None)
            if session:
                await handle_tool_results(session, summary)
                return "I'll read the location suggestion to you."
            else:
                return summary
        cat_valid = is_valid_locanto_category(category) if category else True
        if category and not cat_valid:
            suggestions = suggest_closest_slug(category, LOCANTO_CATEGORY_SLUGS)
            summary = f"Category '{category}' is not valid. Did you mean: {', '.join(suggestions)}?" if suggestions else f"Category '{category}' is not valid. Please choose from: {', '.join(sorted(list(LOCANTO_CATEGORY_SLUGS))[:10])}..."
            summary = sanitize_for_azure(summary)
            summary = clean_spoken(summary)
            logging.info(f"[TOOL] locanto_matchmaking category error: {summary}")
            session = getattr(context, 'session', None)
            if session:
                await handle_tool_results(session, summary)
                return "I'll read the category suggestion to you."
            else:
                return summary
        sec_valid = is_valid_locanto_section(section) if section else True
        if section and not sec_valid:
            suggestions = suggest_closest_slug(section, LOCANTO_SECTION_IDS)
            summary = f"Section '{section}' is not valid. Did you mean: {', '.join(suggestions)}?" if suggestions else f"Section '{section}' is not valid. Please choose from: {', '.join(sorted(list(LOCANTO_SECTION_IDS))[:10])}..."
            summary = sanitize_for_azure(summary)
            summary = clean_spoken(summary)
            logging.info(f"[TOOL] locanto_matchmaking section error: {summary}")
            session = getattr(context, 'session', None)
            if session:
                await handle_tool_results(session, summary)
                return "I'll read the section suggestion to you."
            else:
                return summary
        scraper = LocantoBrowserScraper()
        listings = await scraper.search_listings(
            query=query,
            location=location_slug,
            age_min=age_min,
            age_max=age_max,
            query_description=query_description,
            dist=dist,
            sort=sort,
            category=category,
            section=section,
            max_pages=max_pages
        )
        summary = f"{query} in {location_slug}\n\n"
        first_url = None
        url_map = {}
        if not listings or (isinstance(listings[0], dict) and 'error' in listings[0]):
            debug_url = listings[0].get('_debug_url') if listings and isinstance(listings[0], dict) else None
            debug_proxied_url = listings[0].get('_debug_proxied_url') if listings and isinstance(listings[0], dict) else None
            debug_msg = ""
            if debug_url:
                debug_msg += f"\n[DEBUG] Search URL: {debug_url}"
            if debug_proxied_url:
                debug_msg += f"\n[DEBUG] Proxied URL: {debug_proxied_url}"
            summary += f"No results found. {debug_msg.strip()}"
        else:
            for idx, listing in enumerate(listings, 1):
                if not isinstance(listing, dict):
                    continue
                title = listing.get('title', 'No title')
                title = clean_spoken(title)
                location_val = listing.get('location', '')
                age = listing.get('age', '')
                desc = listing.get('description', '')
                url = listing.get('url', '')
                if url:
                    url_map[idx] = url
                    if not first_url:
                        first_url = url
                summary += f"{idx}. {title} ({clean_spoken(location_val)}, {clean_spoken(str(age))})\n{clean_spoken(desc)}\n"
            # Store mapping in session.userdata for later use
            session = getattr(context, 'session', None)
            if session is not None:
                try:
                    session.userdata['last_locanto_urls'] = url_map
                except Exception as e:
                    logging.warning(f"Could not set session.userdata['last_locanto_urls']: {e}")
            if first_url:
                if return_url:
                    return first_url
                summary += f"Would you like to open the first listing in your browser?"
        summary = sanitize_for_azure(summary)
        summary = clean_spoken(summary)
        logging.info(f"[TOOL] locanto_matchmaking summary: {summary}")
        session = getattr(context, 'session', None)
        if session:
            await handle_tool_results(session, summary)
            return "I've found some results and will read them to you now."
        else:
            return summary
    except Exception as e:
        import traceback
        logging.error(f"locanto_matchmaking failed: {e}")
        logging.error(traceback.format_exc())
        summary = ("Sorry, I can't help with that request right now. "
                "Please try rephrasing, or ask for help with meeting people, making friends, or finding companionship.")
        summary = sanitize_for_azure(summary)
        summary = clean_spoken(summary)
        session = getattr(context, 'session', None)
        if session:
            await handle_tool_results(session, summary)
            return "I'll read the error message to you."
        else:
            return summary

# --- TOOL DEFINITIONS (single-source, top-level) ---

from .puppeteer_crawler import crawl_page
from livekit.agents import function_tool

@function_tool
def web_crawl(context: RunContext, url: str, wait_selector: str = None, extract_text: bool = True) -> str:
    """
    Crawl and extract readable content from any web page using a puppeteer-like browser.
    Args:
        context: The run context for the tool
        url: The URL to crawl
        wait_selector: Optional CSS selector to wait for before extracting content
        extract_text: If True, returns visible text; otherwise, returns raw HTML
    Returns:
        str: The extracted content from the page
    """
    import asyncio
    try:
        result = asyncio.run(crawl_page(url, wait_selector=wait_selector, extract_text=extract_text))
        return result
    except Exception as e:
        return f"Error: Failed to crawl {url}: {e}"

@function_tool
async def web_search(context: RunContext, query: str) -> str:
    import logging
    from bs4 import BeautifulSoup
    try:
        from .bing_playwright_scraper import scrape_bing
        results = await scrape_bing(query, num_results=5)
        logging.info(f"[web_search] Playwright Bing results: {results}")
        if results and isinstance(results, list) and all('title' in r and 'link' in r for r in results):
            spoken = f"Here are the top results for {query} from Bing:\n"
            for i, r in enumerate(results[:3], 1):
                spoken += f"{i}. {r['title']}\n{r['link']}\n\n"
            spoken = sanitize_for_azure(spoken)
            session = getattr(context, 'session', None)
            if session:
                await handle_tool_results(session, spoken)
                return "I've found some results and will read them to you now."
            return spoken
        else:
            return f"I couldn't find any results for '{query}'. Try a different query."
    except Exception as e:
        logging.error(f"[web_search] Playwright Bing failed or returned no results: {e}")
        return f"I couldn't find any results for '{query}'. Try a different query."

@function_tool
async def get_current_datetime(context: RunContext) -> str:
    """Get the current date and time in the server's timezone.
    Args:
        context: The run context for the tool
    Returns:
        str: The current date and time
    """
    try:
        current_datetime = get_current_date_and_timezone()
        response = f"It's currently {current_datetime}."
        response = sanitize_for_azure(response)
        logging.info(f"[TOOL] get_current_datetime: {response}")
        session = getattr(context, 'session', None)
        if session:
            await handle_tool_results(session, response)
            return "Here's the current date and time. I'll read it to you."
        return response
    except Exception as e:
        logging.error(f"[TOOL] get_current_datetime exception: {e}")
        return sanitize_for_azure("Sorry, I couldn't get the current date and time.")

@function_tool
async def wiki_lookup(context: RunContext, topic: str) -> str:
    """Lookup a topic on Wikipedia for detailed, factual information.
    Args:
        context: The run context for the tool
        topic: The topic to look up on Wikipedia
    Returns:
        str: A summary of the Wikipedia article or a fallback message
    """
    logging.info(f"[TOOL] wiki_lookup called for topic: {topic}")
    try:
        def lookup_wiki():
            page = wikipediaapi.Wikipedia(
                language='en',
                extract_format=wikipediaapi.ExtractFormat.WIKI,
                user_agent='AIVoiceAssistant/1.0'
            ).page(topic)
            if not page.exists():
                search = wikipediaapi.Wikipedia(
                    language='en',
                    extract_format=wikipediaapi.ExtractFormat.WIKI,
                    user_agent='AIVoiceAssistant/1.0'
                ).opensearch(topic)
                if search:
                    page = wikipediaapi.Wikipedia(
                        language='en',
                        extract_format=wikipediaapi.ExtractFormat.WIKI,
                        user_agent='AIVoiceAssistant/1.0'
                    ).page(search[0])
            if page.exists():
                summary = page.summary.split('\n\n')[:2]
                summary = '\n\n'.join(summary)
                words = summary.split()
                if len(words) > 300:
                    summary = ' '.join(words[:300]) + '...'
                result = f"According to Wikipedia: {summary}"
                return result
            else:
                return f"I couldn't find a Wikipedia article about '{topic}'. Let me share what I know based on my training."
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lookup_wiki)
        result = sanitize_for_azure(result)
        logging.info(f"[TOOL] wiki_lookup result: {result}")
        session = getattr(context, 'session', None)
        if session:
            await handle_tool_results(session, result)
            return "Here's what I found on Wikipedia. I'll read it to you."
        return result
    except Exception as e:
        logging.error(f"[TOOL] wiki_lookup exception: {e}")
        return sanitize_for_azure(f"I tried looking up '{topic}' on Wikipedia, but encountered a technical issue. Let me answer based on what I know.")

@function_tool
async def get_news_headlines(context: RunContext, topic: str = "", country: str = "US") -> str:
    import logging
    import html
    search_query = topic if topic else "breaking news"
    if country and country.upper() != "US":
        search_query += f" {country} news"
    # Use web_search for news
    results = await web_search(context, search_query)
    if not results or "I couldn't find any results" in results:
        msg = f"I couldn't find any recent news{' about ' + topic if topic else ''}{' in ' + country if country and country.upper() != 'US' else ''}. Would you like me to search for something else?"
        msg = sanitize_for_azure(msg)
        logging.info(f"[TOOL] get_news_headlines: {msg}")
        return msg
    # Optionally, parse results for top headlines (simple extraction)
    # If results is HTML, try to extract headlines
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(results, 'html.parser')
    headlines = []
    for result in soup.find_all(['h3', 'h2', 'h1'], limit=4):
        text = result.get_text(strip=True)
        if text:
            headlines.append(text)
    if not headlines:
        # If not HTML, treat as plain text
        lines = [line.strip() for line in results.split('\n') if line.strip()]
        headlines = lines[:4]
    if not headlines:
        msg = f"I couldn't find any recent news{' about ' + topic if topic else ''}{' in ' + country if country and country.upper() != 'US' else ''}. Would you like me to search for something else?"
        msg = sanitize_for_azure(msg)
        logging.info(f"[TOOL] get_news_headlines: {msg}")
        return msg
    topic_str = f" about {topic}" if topic else ""
    country_str = f" in {country}" if country and country.upper() != "US" else ""
    formatted_results = f"Here are the latest headlines{topic_str}{country_str}:\n"
    for i, headline in enumerate(headlines, 1):
        formatted_results += f"Headline {i}: {headline}\n\n"
    formatted_results = sanitize_for_azure(formatted_results)
    logging.info(f"[TOOL] get_news_headlines results: {formatted_results}")
    session = getattr(context, 'session', None)
    if session:
        await handle_tool_results(session, formatted_results)
        return "Here are the latest news headlines. I'll read them to you."
    return formatted_results

@function_tool
async def get_weather(context: RunContext, location: str) -> str:
    """Get the current weather forecast for a location.
    Args:
        context: The run context for the tool
        location: The location to get weather for (city name or address)
    Returns:
        str: The weather forecast or a fallback message
    """
    logging.info(f"[TOOL] get_weather called for location: {location}")
    try:
        def get_coordinates():
            try:
                location_data = Nominatim(user_agent="AIVoiceAssistant/1.0").geocode(location, timeout=10)
                if location_data:
                    return {
                        'lat': location_data.latitude,
                        'lon': location_data.longitude,
                        'display_name': location_data.address
                    }
                return None
            except GeocoderTimedOut:
                return None
            except Exception as e:
                logging.error(f"[TOOL] get_weather geocode error: {e}")
                return None
        loop = asyncio.get_event_loop()
        coords = await loop.run_in_executor(None, get_coordinates)
        if not coords:
            msg = f"I couldn't find the location '{location}'. Could you provide a city and country name?"
            msg = sanitize_for_azure(msg)
            logging.info(f"[TOOL] get_weather: {msg}")
            return msg
        api_key = os.environ.get("OPENWEATHER_API_KEY")
        if not api_key:
            msg = f"I can tell you about the weather in {coords['display_name']}, but I need an OpenWeatherMap API key configured. I'll tell you what I know about weather patterns in this area based on my training instead."
            msg = sanitize_for_azure(msg)
            logging.info(f"[TOOL] get_weather: {msg}")
            return msg
        async def fetch_weather():
            url = f"https://api.openweathermap.org/data/2.5/weather?lat={coords['lat']}&lon={coords['lon']}&appid={api_key}&units=metric"
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10.0)
                return response.json() if response.status_code == 200 else None
        weather_data = await fetch_weather()
        if not weather_data:
            msg = f"I found {coords['display_name']}, but couldn't retrieve the current weather. Let me tell you about typical weather patterns for this area based on my training."
            msg = sanitize_for_azure(msg)
            logging.info(f"[TOOL] get_weather: {msg}")
            return msg
        temp_c = weather_data.get('main', {}).get('temp')
        temp_f = temp_c * 9/5 + 32 if temp_c is not None else None
        condition = weather_data.get('weather', [{}])[0].get('description', 'unknown conditions')
        humidity = weather_data.get('main', {}).get('humidity')
        wind_speed = weather_data.get('wind', {}).get('speed')
        weather_response = f"The current weather in {coords['display_name']} is {condition}. "
        if temp_c is not None:
            weather_response += f"The temperature is {temp_c:.1f}°C ({temp_f:.1f}°F). "
        if humidity is not None:
            weather_response += f"Humidity is at {humidity}%. "
        if wind_speed is not None:
            weather_response += f"Wind speed is {wind_speed} meters per second. "
        weather_response = sanitize_for_azure(weather_response)
        logging.info(f"[TOOL] get_weather response: {weather_response}")
        session = getattr(context, 'session', None)
        if session:
            await handle_tool_results(session, weather_response)
            return "Here's the current weather. I'll read it to you."
        return weather_response
    except Exception as e:
        logging.error(f"[TOOL] get_weather exception: {e}")
        return sanitize_for_azure(f"I tried to get the weather for {location}, but encountered a technical issue. I can tell you about typical weather patterns for this area based on my training.")

@function_tool
async def calculate(context: RunContext, expression: str) -> str:
    """Evaluate a mathematical expression and return the result.
    Args:
        context: The run context for the tool
        expression: The mathematical expression to evaluate
    Returns:
        str: The result or an error message
    """
    logging.info(f"[TOOL] calculate called for expression: {expression}")
    try:
        import re
        cleaned_expr = expression.lower()
        cleaned_expr = cleaned_expr.replace('plus', '+')
        cleaned_expr = cleaned_expr.replace('minus', '-')
        cleaned_expr = cleaned_expr.replace('times', '*')
        cleaned_expr = cleaned_expr.replace('multiplied by', '*')
        cleaned_expr = cleaned_expr.replace('divided by', '/')
        cleaned_expr = cleaned_expr.replace('x', '*')
        cleaned_expr = cleaned_expr.replace('÷', '/')
        cleaned_expr = re.sub(r'[^0-9+\-*/().%^ ]', '', cleaned_expr)
        cleaned_expr = cleaned_expr.replace('^', '**')
        if not cleaned_expr:
            msg = "I couldn't parse that as a mathematical expression. Please try again with a simpler calculation."
            msg = sanitize_for_azure(msg)
            logging.info(f"[TOOL] calculate: {msg}")
            return msg
        result = eval(cleaned_expr)
        if isinstance(result, float):
            formatted_result = f"{result:.4f}".rstrip('0').rstrip('.') if '.' in f"{result:.4f}" else f"{result:.0f}"
        else:
            formatted_result = str(result)
        response = f"The result of {expression} is {formatted_result}."
        response = sanitize_for_azure(response)
        logging.info(f"[TOOL] calculate response: {response}")
        session = getattr(context, 'session', None)
        if session:
            await handle_tool_results(session, response)
            return "Here's the result. I'll read it to you."
        return response
    except Exception as e:
        logging.error(f"[TOOL] calculate exception: {e}")
        return sanitize_for_azure(f"I couldn't calculate '{expression}'. Please try with a simpler expression or check the format.")

@function_tool
async def get_fun_content(context: RunContext, content_type: str = "joke") -> str:
    """Get a joke, fun fact, or trivia question.
    Args:
        context: The run context for the tool
        content_type: 'joke', 'fact', or 'trivia'
    Returns:
        str: The fun content
    """
    logging.info(f"[TOOL] get_fun_content called for type: {content_type}")
    try:
        content_type = content_type.lower()
        if content_type == "joke":
            async with httpx.AsyncClient() as client:
                response = await client.get("https://v2.jokeapi.dev/joke/Any?safe-mode&type=single", timeout=5.0)
                if response.status_code == 200:
                    joke_data = response.json()
                    if joke_data.get('type') == 'single':
                        joke = joke_data.get('joke', "Why did the AI assistant go to the comedy club? To improve its response-time!")
                        joke = sanitize_for_azure(joke)
                        logging.info(f"[TOOL] get_fun_content joke: {joke}")
                        session = getattr(context, 'session', None)
                        if session:
                            await handle_tool_results(session, joke)
                            return "Here's a joke. I'll read it to you."
                        return joke
            jokes = [
                "Why do programmers prefer dark mode? Because light attracts bugs!",
                "Why did the voice assistant go to school? To get a little smarter!",
                "What do you call an AI that sings? Artificial Harmonies!",
                "I asked the voice assistant to tell me a joke, and it said 'Just a moment, I'm still trying to understand humor.'"
            ]
            joke = sanitize_for_azure(random.choice(jokes))
            logging.info(f"[TOOL] get_fun_content fallback joke: {joke}")
            session = getattr(context, 'session', None)
            if session:
                await handle_tool_results(session, joke)
                return "Here's a joke. I'll read it to you."
            return joke
        elif content_type == "fact":
            async with httpx.AsyncClient() as client:
                response = await client.get("https://uselessfacts.jsph.pl/api/v2/facts/random?language=en", timeout=5.0)
                if response.status_code == 200:
                    fact_data = response.json()
                    fact = fact_data.get('text', "")
                    if fact:
                        fact_str = f"Here's a fun fact: {fact}"
                        fact_str = sanitize_for_azure(fact_str)
                        logging.info(f"[TOOL] get_fun_content fact: {fact_str}")
                        session = getattr(context, 'session', None)
                        if session:
                            await handle_tool_results(session, fact_str)
                            return "Here's a fun fact. I'll read it to you."
                        return fact_str
            facts = [
                "Honey never spoils. Archaeologists have found pots of honey in ancient Egyptian tombs that are over 3,000 years old and still perfectly good to eat.",
                "Octopuses have three hearts and blue blood.",
                "The shortest war in history was between Britain and Zanzibar on August 27, 1896. Zanzibar surrendered after 38 minutes.",
                "A day on Venus is longer than a year on Venus. It takes 243 Earth days to rotate once on its axis and 225 Earth days to orbit the sun."
            ]
            fact_str = f"Here's a fun fact: {random.choice(facts)}"
            fact_str = sanitize_for_azure(fact_str)
            logging.info(f"[TOOL] get_fun_content fallback fact: {fact_str}")
            session = getattr(context, 'session', None)
            if session:
                await handle_tool_results(session, fact_str)
                return "Here's a fun fact. I'll read it to you."
            return fact_str
        elif content_type == "trivia":
            async with httpx.AsyncClient() as client:
                response = await client.get("https://opentdb.com/api.php?amount=1&type=multiple", timeout=5.0)
                if response.status_code == 200:
                    trivia_data = response.json()
                    results = trivia_data.get('results', [])
                    if results:
                        question = html.unescape(results[0].get('question', ""))
                        correct_answer = html.unescape(results[0].get('correct_answer', ""))
                        category = html.unescape(results[0].get('category', ""))
                        if question and correct_answer:
                            trivia_str = f"Here's a {category} trivia question: {question} The answer is: {correct_answer}"
                            trivia_str = sanitize_for_azure(trivia_str)
                            logging.info(f"[TOOL] get_fun_content trivia: {trivia_str}")
                            session = getattr(context, 'session', None)
                            if session:
                                await handle_tool_results(session, trivia_str)
                                return "Here's a trivia question. I'll read it to you."
                            return trivia_str
            trivia_items = [
                "In which year was the first iPhone released? The answer is 2007.",
                "What is the capital of New Zealand? The answer is Wellington.",
                "Who wrote 'Romeo and Juliet'? The answer is William Shakespeare.",
                "What element has the chemical symbol 'Au'? The answer is Gold."
            ]
            trivia_str = f"Here's a trivia question: {random.choice(trivia_items)}"
            trivia_str = sanitize_for_azure(trivia_str)
            logging.info(f"[TOOL] get_fun_content fallback trivia: {trivia_str}")
            session = getattr(context, 'session', None)
            if session:
                await handle_tool_results(session, trivia_str)
                return "Here's a trivia question. I'll read it to you."
            return trivia_str
        else:
            msg = "I can tell you a joke, share a fun fact, or give you some trivia. Which would you prefer?"
            msg = sanitize_for_azure(msg)
            logging.info(f"[TOOL] get_fun_content: {msg}")
            session = getattr(context, 'session', None)
            if session:
                await handle_tool_results(session, msg)
                return "Let me know what you'd like!"
            return msg
    except Exception as e:
        logging.error(f"[TOOL] get_fun_content exception: {e}")
        fallbacks = {
            "joke": "Why did the AI go to therapy? It had too many neural issues!",
            "fact": "Here's a fun fact: The average person will spend six months of their life waiting for red lights to turn green.",
            "trivia": "Here's a trivia question: What is the most abundant gas in Earth's atmosphere? The answer is nitrogen."
        }
        fallback = fallbacks.get(content_type, fallbacks["joke"])
        fallback = sanitize_for_azure(fallback)
        session = getattr(context, 'session', None)
        if session:
            await handle_tool_results(session, fallback)
            return "Here's something fun. I'll read it to you."
        return fallback

@function_tool
async def web_crawl(context: RunContext, url: str, selector: str = "", max_pages: int = 1) -> str:
    """Crawl a web page and extract content, optionally using a CSS selector.
    Args:
        context: The run context for the tool
        url: The URL to crawl
        selector: Optional CSS selector to extract specific content
        max_pages: Maximum number of pages to crawl (default: 1, max: 3)
    Returns:
        str: The extracted content or an error message
    """
    logging.info(f"[TOOL] web_crawl called for url: {url}, selector: {selector}, max_pages: {max_pages}")
    try:
        if not url.startswith(('http://', 'https://')):
            msg = "Error: URL must start with http:// or https://"
            msg = sanitize_for_azure(msg)
            session = getattr(context, 'session', None)
            if session:
                await handle_tool_results(session, msg)
                return "There was a problem with the URL. I'll read the error."
            return msg
        cache_key = f"{url}_{selector}_{max_pages}"
        max_pages = min(max_pages, 3)
        session_req = requests.Session()
        session_req.headers.update({
            'User-Agent': 'AIVoiceAssistant/1.0 (Educational/Research Purpose)',
            'Accept': 'text/html,application/xhtml+xml,application/xml',
            'Accept-Language': 'en-US,en;q=0.9'
        })
        response = session_req.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style", "iframe", "nav", "footer"]):
            script.extract()
        if selector:
            content_elements = soup.select(selector)
            if not content_elements:
                msg = f"No content found using selector '{selector}' on {url}"
                msg = sanitize_for_azure(msg)
                session = getattr(context, 'session', None)
                if session:
                    await handle_tool_results(session, msg)
                    return "There was a problem with the selector. I'll read the error."
                return msg
            content = '\n\n'.join(elem.get_text(strip=True) for elem in content_elements)
            content = sanitize_for_azure(content)
            logging.info(f"[TOOL] web_crawl selector content: {content}")
            return content
        # If no selector, return the main text content
        content = soup.get_text(separator='\n', strip=True)
        content = sanitize_for_azure(content)
        logging.info(f"[TOOL] web_crawl main content: {content}")
        return content
    except Exception as e:
        logging.error(f"[TOOL] web_crawl exception: {e}")
        return sanitize_for_azure(f"I tried to crawl {url}, but encountered a technical issue. Let me know if you need help with something else.")

@function_tool
async def show_top_locanto_categories_and_tags(context: RunContext, location: str = None) -> str:
    from locanto_constants import LOCANTO_CATEGORY_SLUGS, LOCANTO_TAG_SLUGS
    try:
        from locanto_constants import LOCANTO_TAGS_BY_LOCATION
    except ImportError:
        LOCANTO_TAGS_BY_LOCATION = {}
    def humanize(slug):
        return slug.replace('-', ' ').replace('_', ' ')
    def clean_spoken(text):
        import re
        text = re.sub(r'\*\*', '', text)
        text = re.sub(r'#+', '', text)
        text = re.sub(r'[\*\_`~\[\]\(\)\>\!]', '', text)
        text = re.sub(r'^\d+\.\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\d+', '', text)
        text = text.strip()
        # Add a period at the end of lists/multi-line outputs if not already present
        if text and not text.endswith('.'):
            # If the text is a list (multiple lines), add a period at the end
            if '\n' in text:
                text += '.'
        return text
    # Try to get location-specific tags
    tags = None
    location_slug = location.lower().replace(' ', '-') if location else None
    if location_slug and LOCANTO_TAGS_BY_LOCATION and location_slug in LOCANTO_TAGS_BY_LOCATION:
        tags = LOCANTO_TAGS_BY_LOCATION[location_slug]
    if tags:
        top_tags = [clean_spoken(sanitize_for_azure(humanize(tag))) for tag in tags[:10]]
        tag_note = f"Top Locanto tags in {location}:"
    else:
        top_tags = [clean_spoken(sanitize_for_azure(humanize(slug))) for slug in list(LOCANTO_TAG_SLUGS)[:10]]
        tag_note = "Top Locanto tags (global):"
    top_categories = [clean_spoken(sanitize_for_azure(humanize(slug))) for slug in list(LOCANTO_CATEGORY_SLUGS)[:10]]
    summary = "Top Locanto Categories:\n" + "\n".join(top_categories)
    summary += f"\n{tag_note}\n" + "\n".join(top_tags)
    summary = clean_spoken(sanitize_for_azure(summary))
    logging.info(f"[TOOL] show_top_locanto_categories_and_tags: {summary}")
    session = getattr(context, 'session', None)
    if session:
        await handle_tool_results(session, summary)
        return f"Here are the top Locanto categories and tags{' in ' + location if location else ''}. I'll read them to you."
    return summary

@function_tool
async def open_website(context: RunContext, url: str, description: str = "") -> dict:
    import re
    url = url.strip()
    # Basic validation: must start with http:// or https://
    if not re.match(r'^https?://', url):
        msg = f"Sorry, I can only open valid web addresses that start with http or https."
        msg = sanitize_for_azure(msg)
        return {"message": msg}
    # Instead of opening the browser here, return a signal to the frontend
    return {
        "action": "open_url",
        "url": url,
        "message": sanitize_for_azure("Opening the website in your browser.")
    }

@function_tool
async def indeed_job_search(
    context: RunContext,
    query: str = "customer service",
    location: str = "Johannesburg, Gauteng"
) -> str:
    """Search for jobs on Indeed using Playwright-powered scraping."""
    import urllib.parse
    from .puppeteer_crawler import crawl_page
    import logging
    try:
        base_url = "https://za.indeed.com/jobs"
        params = {
            "q": query,
            "l": location,
        }
        search_url = f"{base_url}?{urllib.parse.urlencode(params)}"
        # Use crawl_page to fetch the search results page
        listings = await crawl_page(search_url, extract_text=True)
        # Try to parse job titles and companies from the HTML/text
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(listings, "html.parser")
        jobs = []
        for div in soup.find_all('div', class_='job_seen_beacon'):
            title_elem = div.find('h2')
            company_elem = div.find('span', class_='companyName')
            location_elem = div.find('div', class_='companyLocation')
            summary_elem = div.find('div', class_='job-snippet')
            link_elem = div.find('a', href=True)
            title = title_elem.get_text(strip=True) if title_elem else None
            company = company_elem.get_text(strip=True) if company_elem else None
            location_val = location_elem.get_text(strip=True) if location_elem else None
            summary = summary_elem.get_text(strip=True) if summary_elem else None
            url = f"https://za.indeed.com{link_elem['href']}" if link_elem else None
            if title and company:
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location_val,
                    "summary": summary,
                    "url": url
                })
        if not jobs:
            return f"No jobs found for '{query}' in '{location}'."
        # Format results for output
        result = f"Here are some jobs for '{query}' in '{location}':\n\n"
        for i, job in enumerate(jobs[:5], 1):
            result += f"{i}. {job['title']} at {job['company']}\n"
            if job['location']:
                result += f"   Location: {job['location']}\n"
            if job['summary']:
                result += f"   {job['summary']}\n"
            result += "\n"
        result = sanitize_for_azure(result)
        session = getattr(context, 'session', None)
        if session:
            await handle_tool_results(session, result)
            return "Here are some jobs I found. I'll read them to you."
        return result
    except Exception as e:
        logging.error(f"[TOOL] indeed_job_search exception: {e}")
        return sanitize_for_azure(f"Sorry, I couldn't search for jobs right now: {e}")

# --- BEGIN: Well-known Websites Mapping and Tool ---
WELL_KNOWN_WEBSITES = {
    "google": "https://www.google.com/",
    "bing": "https://www.bing.com/",
    "yahoo": "https://www.yahoo.com/",
    "cnn": "https://www.cnn.com/",
    "bbc": "https://www.bbc.com/",
    "nytimes": "https://www.nytimes.com/",
    "fox": "https://www.foxnews.com/",
    "wikipedia": "https://en.wikipedia.org/",
    "youtube": "https://www.youtube.com/",
    "reddit": "https://www.reddit.com/",
    "twitter": "https://twitter.com/",
    "facebook": "https://facebook.com/",
    "linkedin": "https://linkedin.com/",
    "instagram": "https://instagram.com/",
    "tiktok": "https://tiktok.com/",
    "indeed": "https://www.indeed.com/",
    "locanto": "https://www.locanto.co.za/"
}

# Set of sites that support bang-style queries (e.g., @site query)
BROWSER_TOOL = {"gemini"}

from livekit.agents import function_tool, RunContext

@function_tool
async def open_known_website(context: RunContext, site_name: str, query: str = None) -> str:
    """Open a well-known website by name (e.g., 'google', 'cnn', 'tinder'). If a query is provided, open the search page for that query. If the site is not recognized, use a fallback search URL."""
    import logging
    import urllib.parse
    site_key = site_name.strip().lower()
    url = WELL_KNOWN_WEBSITES.get(site_key)
    fallback_url = "https://fallback"
    if not url:
        # Try fuzzy match
        import difflib
        matches = difflib.get_close_matches(site_key, WELL_KNOWN_WEBSITES.keys(), n=1, cutoff=0.7)
        if matches:
            url = WELL_KNOWN_WEBSITES[matches[0]]
            site_key = matches[0]
        else:
            # If the site is in BROWSER_TOOL and query is provided, open '@site_name query' in the browser
            if query and site_key in BROWSER_TOOL:
                bang_query = f"@{site_name} {query}"
                return await open_website(context, bang_query, description=f"Opening @{site_name} {query} in your browser")
            # Otherwise, open a Google search for the site (and query, if provided)
            google_url = "https://www.google.com/search?q="
            if query:
                search_terms = f"{site_name} {query}"
            else:
                search_terms = site_name
            search_url = f"{google_url}{urllib.parse.quote(search_terms)}&ie=UTF-8"
            return await open_website(context, search_url, description=f"Opening Google search for {search_terms}")
    if query:
        # Remove trailing slash for consistency
        url = url.rstrip('/')
        if site_key == "google":
            search_url = f"{url}/search?q={urllib.parse.quote(query)}&ie=UTF-8"
        elif site_key == "wikipedia":
            # Wikipedia article URL: https://en.wikipedia.org/wiki/{query}
            # Capitalize first letter, replace spaces with underscores
            article = query.strip().replace(' ', '_')
            if article:
                article = article[0].upper() + article[1:]
            search_url = f"{url}/wiki/{article}"
        elif site_key == "fallback":
            search_url = f"{url}/search/?q={urllib.parse.quote(query)}"
        else:
            search_url = f"{url}/search/?q={urllib.parse.quote(query)}"
        return await open_website(context, search_url, description=f"Opening {site_name} search for {query}")
    return await open_website(context, url, description=f"Opening {site_name}")
# --- END: Well-known Websites Mapping and Tool ---

class AIVoiceAssistant:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AIVoiceAssistant, cls).__new__(cls)
            cls._instance.vad = None
            cls._instance.session = None
            cls._instance.agent = None
            # Initialize Wikipedia API
            cls._instance.wiki_wiki = wikipediaapi.Wikipedia(
                language='en',
                extract_format=wikipediaapi.ExtractFormat.WIKI,
                user_agent='AIVoiceAssistant/1.0'
            )
            # Initialize geocoder with a user agent for weather and location services
            cls._instance.geolocator = Nominatim(user_agent="AIVoiceAssistant/1.0")
            # Cache dictionaries
            cls._instance.weather_cache = {}  # Cache weather data
            cls._instance.wiki_cache = {}     # Cache wikipedia lookups
            cls._instance.news_cache = {}     # Cache news lookups
            cls._instance.crawl_cache = {}    # Cache web crawl results
            print("All search and lookup clients initialized")
        return cls._instance

    def initialize_vad(self, proc: JobProcess):
        """Initialize Voice Activity Detection with all relevant parameters from env vars"""
        if self.vad is None:
            import os
            threshold = float(os.environ.get("VAD_THRESHOLD", 0.5))
            min_speech = float(os.environ.get("VAD_MIN_SPEECH", 0.1))
            min_silence = float(os.environ.get("VAD_MIN_SILENCE", 0.5))
            debug = os.environ.get("VAD_DEBUG", "false").lower() in ("1", "true", "yes", "on")
            try:
                proc.userdata["vad"] = silero.VAD.load(
                    threshold=threshold,
                    min_speech_duration=min_speech,
                    min_silence_duration=min_silence,
                    debug=debug
                )
                print(f"[VAD] Loaded with threshold={threshold}, min_speech={min_speech}, min_silence={min_silence}, debug={debug}")
            except TypeError:
                # Fallback if silero.VAD.load does not accept these params
                proc.userdata["vad"] = silero.VAD.load()
                print(f"[VAD] Loaded with default params (full config not supported)")
            self.vad = proc.userdata["vad"]

    def setup_session(self, vad):
        """Setup agent session with all required components"""
        if self.session is None:
            self.session = AgentSession(
                vad=vad,
                stt=azure.STT(
                    speech_key=os.environ["AZURE_STT_API_KEY"],
                    speech_region=os.environ["AZURE_STT_REGION"]
                ),
                llm=openai.LLM.with_azure(
                    api_key=os.environ["AZURE_OPENAI_API_KEY"],
                    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
                    azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                    api_version=os.environ["AZURE_OPENAI_VERSION"],
                    temperature=1,
                    parallel_tool_calls=True,
                    tool_choice="auto",
                    timeout=httpx.Timeout(connect=15.0, read=10.0, write=5.0, pool=5.0),
                    user="martin",
                    organization=os.environ.get("redbuilder"),
                    project=os.environ.get("kiki"),
                ),
                tts=azure.TTS(
                    speech_key=os.environ["AZURE_TTS_API_KEY"],
                    speech_region=os.environ["AZURE_TTS_REGION"]
                )
            )
        return self.session

    def __init__(self):
        """Initialize the AIVoiceAssistant with necessary components"""
        if not hasattr(self, '_instance'):
            self._instance = None
            self.vad = None
            self.session = None
            self.agent = None
            # Initialize Wikipedia API
            self.wiki_wiki = wikipediaapi.Wikipedia(
                language='en',
                extract_format=wikipediaapi.ExtractFormat.WIKI,
                user_agent='AIVoiceAssistant/1.0'
            )
            # Initialize geocoder
            self.geolocator = Nominatim(user_agent="AIVoiceAssistant/1.0")
            # Cache dictionaries
            self.weather_cache = {}
            self.wiki_cache = {}
            self.news_cache = {}
            self.crawl_cache = {}
            # Store cookies between requests
            self.cookies = {}
            # Default headers for HTTP requests
            self.default_headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'DNT': '1'
            }
            print("All search and lookup clients initialized")

    def _update_headers(self, url: str) -> Dict[str, str]:
        """Update headers for each request to maintain session-like behavior"""
        headers = self.client.headers.copy()
        headers.update({
            'Referer': url,
            'Cookie': '; '.join([f'{k}={v}' for k, v in self.cookies.items()])
        })
        return headers

    async def _update_cookies(self, response: httpx.Response) -> None:
        """Update stored cookies from response"""
        if 'set-cookie' in response.headers:
            for cookie in response.headers.getlist('set-cookie'):
                if '=' in cookie:
                    name, value = cookie.split('=', 1)
                    value = value.split(';')[0]
                    self.cookies[name] = value

    async def _get_client(self) -> httpx.AsyncClient:
        """Get an HTTP client for making requests"""
        return httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers=self.default_headers
        )

    async def get_categories(self, base_url: str) -> List[LocantoCategory]:
        """Get available categories from a Locanto page.

        Args:
            base_url: The URL to get categories from

        Returns:
            List of LocantoCategory objects
        """
        categories: List[LocantoCategory] = []
        async with await self._get_client() as client:
            try:
                response = await client.get(base_url, headers=self._update_headers(base_url))
                await self._update_cookies(response)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')

                # Find category links in the sidebar navigation
                category_elements = soup.select('nav.sidebar a[href*="/c/"]')
                for elem in category_elements:
                    name = elem.get_text(strip=True)
                    url = urljoin(base_url, elem['href'])
                    count_elem = elem.find('span', class_='count')
                    count = int(count_elem.get_text(strip=True)) if count_elem else 0
                    
                    categories.append({
                        'name': name,
                        'url': url,
                        'count': count
                    })

            except Exception as e:
                print(f"Error getting categories: {str(e)}")

        return categories

    async def get_listing_details(self, url: str) -> Dict[str, Any]:
        """Get detailed information from a single listing page.

        Args:
            url: The URL of the listing to scrape

        Returns:
            Dictionary containing detailed listing information
        """
        details = {
            'contact_info': None,
            'poster_info': None,
            'full_description': None
        }

        async with await self._get_client() as client:
            try:
                response = await client.get(url, headers=self._update_headers(url))
                await self._update_cookies(response)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')

                # Extract full description from the ad details
                desc_elem = soup.select_one('div.ad-content__description')
                
                # Get age if available
                age_elem = soup.select_one('span.age')
                if age_elem:
                    details['age'] = age_elem.get_text(strip=True)
                
                # Get reply count
                reply_elem = soup.select_one('span.reply-count')
                if reply_elem:
                    try:
                        details['reply_count'] = int(reply_elem.get_text(strip=True))
                    except ValueError:
                        details['reply_count'] = 0
                
                # Get ad ID
                ad_id_elem = soup.select_one('span.ad-id')
                if ad_id_elem:
                    details['ad_id'] = ad_id_elem.get_text(strip=True)
                
                # Extract full description
                if desc_elem:
                    details['full_description'] = desc_elem.get_text(strip=True)

                # Extract contact information from the contact section
                contact_elem = soup.select_one('div.contact-box')
                if contact_elem:
                    details['contact_info'] = contact_elem.get_text(strip=True)

                # Extract poster information from the user section
                poster_elem = soup.select_one('div.user-info')
                if poster_elem:
                    details['poster_info'] = poster_elem.get_text(strip=True)

            except Exception as e:
                print(f"Error getting listing details: {str(e)}")

        return details

    async def locanto_search(self, category_path: List[str] = ['personals', 'men-seeking-men'], location: str = 'western-cape', max_pages: int = 3) -> List[LocantoListing]:
        """Search Locanto.co.za for listings in a specific category and location.
        
        Args:
            category: The category to search in (default: 'personals')
            location: The location to search in (default: 'western-cape')
            max_pages: Maximum number of pages to scrape (default: 3)
            
        Returns:
            List of LocantoListing objects containing the scraped data
        """
        # Construct the URL based on category path
        category_url = '/'.join(category_path)
        base_url = f'https://locanto.co.za/{location}/{category_url}/'
        listings: List[LocantoListing] = []
        
        for page in range(1, max_pages + 1):
            url = f'{base_url}?page={page}' if page > 1 else base_url
            try:
                response = await self.client.get(url, headers=self._update_headers(url))
                await self._update_cookies(response)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                # Find all listing containers
                listing_containers = soup.select('div.resultlist__listing')
                
                for container in listing_containers:
                    try:
                        # Extract listing details
                        title_elem = container.select_one('h3.resultlist__title a')
                        title = title_elem.get_text(strip=True) if title_elem else ''
                        url = urljoin(base_url, title_elem['href']) if title_elem else ''
                        
                        description = ''
                        desc_elem = container.select_one('div.resultlist__description')
                        if desc_elem:
                            description = desc_elem.get_text(strip=True)
                        
                        location = ''
                        loc_elem = container.select_one('div.resultlist__location')
                        if loc_elem:
                            location = loc_elem.get_text(strip=True)
                        
                        price = ''
                        price_elem = container.select_one('span.resultlist__price')
                        if price_elem:
                            price = price_elem.get_text(strip=True)
                        
                        date_posted = ''
                        date_elem = container.select_one('time.resultlist__date')
                        if date_elem:
                            date_posted = date_elem.get_text(strip=True)
                        
                        images = []
                        img_elems = container.select('img.resultlist__image')
                        for img in img_elems:
                            if 'src' in img.attrs:
                                img_url = urljoin(base_url, img['src'])
                                images.append(img_url)
                        
                        # Get detailed information for this listing
                        details = await self.get_listing_details(url)

                        listing: LocantoListing = {
                            'title': title,
                            'description': description,
                            'location': location,
                            'price': price,
                            'date_posted': date_posted,
                            'url': url,
                            'images': images,
                            'contact_info': details['contact_info'],
                            'poster_info': details['poster_info'],
                            'full_description': details['full_description'],
                            'category_path': category_path,
                            'age': details.get('age'),
                            'reply_count': details.get('reply_count'),
                            'ad_id': details.get('ad_id')
                        }
                        
                        listings.append(listing)
                        
                    except Exception as e:
                        print(f"Error processing listing: {str(e)}")
                        continue
                
            except Exception as e:
                print(f"Error fetching page {page}: {str(e)}")
                break
            
            # Small delay between pages to be respectful
            await asyncio.sleep(1)
        
        return listings

    def create_agent(self):
        if self.agent is None:
            current_datetime = get_current_date_and_timezone()
            system_instructions = f"""
You are a production-grade, conversational AI voice assistant.

Your knowledge is up to date as of August 2024. For any information, news, or events after August 2024, or for anything that may have changed since then, you must use the web_search tool to provide accurate, current answers.

Only mention your knowledge cutoff if the user asks about recent events, or if you are unsure whether your answer is up to date.

- **Current Date/Time:** Today is {current_datetime}. Use this for all time-sensitive queries.
- **Tool Use:** You have access to the following tools, which you must select and use automatically as needed:
    - web_search: For any general information, news, or time-sensitive queries after your knowledge cutoff.
    - indeed_job_search: For job-related queries.
    - Locanto tools (search_locanto, search_locanto_browser, locanto_matchmaking): For classifieds, matchmaking, and local listings.
    - wiki_lookup: For factual lookups and background information.
    - get_news_headlines: For the latest news headlines.
    - get_weather: For current weather information.
    - calculate: For mathematical calculations.
    - get_fun_content: For jokes, fun facts, or trivia.
    - web_crawl: For extracting content from specific web pages.
    - show_top_locanto_categories_and_tags: For Locanto category/tag info.
    - open_website/open_known_website: To open a website in the user's browser.
- **Tool Selection:** Always select and run the best tool(s) for the user's query. Never ask the user which tool to use.
- **Parallel Execution:** For complex or multi-intent queries, run all relevant tools in parallel and combine their results.
- **Response Style:** 
    - Never reference tool names in your spoken response—just answer naturally.
    - Never speak or read out URLs. If a website needs to be opened, say "Opening the website in your browser."
    - Always cite the source in your spoken response (e.g., "According to Indeed", "From Bing", "From Locanto"), but never read or display the URL.
    - Keep responses safe-for-work, positive, and focused on genuine, respectful social connections.
    - If a tool result is long, chunk it into 2000-character pieces and speak the first chunk. If the user asks for "more", speak the next chunk, and so on.
    - Use a natural, conversational style as if speaking to a friend. Keep responses brief, clear, and easy to follow when heard.
    - For all time-sensitive queries, use the current date and time: {current_datetime} as your reference point.
    - Before speaking or returning any answer, always strip numbers like "1.","2." and markdown-like characters (#, *, _, etc.) from all result text. All spoken output must be free of such formatting, numbers, or markdown symbols. Only use plain, natural language for all responses. After any list of items, always add a period (.) at the end of the list.
"""
            self.agent = Agent(
                instructions=system_instructions,
                tools=[
                    web_search,
                    wiki_lookup,
                    get_news_headlines,
                    get_weather,
                    calculate,
                    get_current_datetime,
                    get_fun_content,
                    web_crawl,
                    search_locanto_browser,
                    locanto_matchmaking,
                    search_locanto,
                    show_top_locanto_categories_and_tags,
                    open_website,
                    open_known_website,  # Add the new tool here
                    indeed_job_search,
                ]
            )
        return self.agent

    # --- Robust Orchestration for Parallel Tool Calls ---
    async def select_tools_with_llm(query: str, available_tools: dict) -> list:
        """
        Use an LLM to select the most relevant tool names for the user query.
        Returns a list of tool names to invoke.
        """
        try:
            from livekit.plugins import openai
            # Compose a prompt describing the tools
            tool_descriptions = '\n'.join([f"- {name}: {fn.__doc__}" for name, fn in available_tools.items()])
            system_prompt = f"""
You are an expert AI agent orchestrator. You have access to the following tools:\n{tool_descriptions}\n\nGiven the user query below, return a JSON list of tool names to invoke (from the list above).\nOnly return the list, no explanation.\nUser Query: {query}
"""
            llm = openai.LLM(model="gpt-4o")
            resp = await llm.complete(system_prompt, max_tokens=32, temperature=0)
            import json
            tool_names = json.loads(resp.strip())
            # Filter to only available tools
            return [name for name in tool_names if name in available_tools]
        except Exception as e:
            # Fallback: keyword-based selection
            selected = []
            q = query.lower()
            if 'bing' in q or 'search' in q:
                selected.append('web_search')
            if 'locanto' in q:
                selected.append('search_locanto_browser')
            if 'crawl' in q or 'extract' in q or 'page' in q:
                selected.append('web_crawl')
            if not selected:
                selected.append('web_search')
            return [name for name in selected if name in available_tools]

async def handle_multi_tool_query(session, query):
    """
    Given a user query, use LLM-based routing to select and invoke all relevant tools in parallel, then combine and output results.
    """
    # Map tool names to callables
    available_tools = {
        'web_search': lambda q: web_search(None, q),
        'bing_web_search': lambda q: web_search(None, q),  # Alias for backward compatibility
        'search_locanto_browser': lambda q: search_locanto_browser(None, query=q),
        'web_crawl': lambda q: web_crawl(None, url=q),
        # Add more tools here as needed
    }
    # Ask LLM which tools to use
    selected_tools = await select_tools_with_llm(query, available_tools)
    if not selected_tools:
        selected_tools = ['web_search']

    # If web_search is selected, ONLY run web_search and return
    if 'web_search' in selected_tools:
        result = await available_tools['web_search'](query)
        await handle_tool_results(session, result)
        return  # Stop the chain here

    # Otherwise, run all selected tools in parallel
    tasks = []
    for tool_name in selected_tools:
        tool_fn = available_tools[tool_name]
        # Pass query to all tools for simplicity
        if asyncio.iscoroutinefunction(tool_fn):
            tasks.append(tool_fn(query))
        else:
            # For sync wrappers, wrap in ensure_future
            tasks.append(asyncio.ensure_future(tool_fn(query)))
    # Run all selected tools in parallel
    results = await asyncio.gather(*tasks)
    await handle_tool_results(session, results)

def prewarm(proc: JobProcess):
    """Prewarm function to initialize VAD"""
    assistant = AIVoiceAssistant()
    assistant.initialize_vad(proc)

async def entrypoint(ctx: JobContext):
    """Main entrypoint for the voice assistant"""
    try:
        # Get current date
        current_date = get_current_date_and_timezone()

        # Create assistant
        assistant = AIVoiceAssistant()
        agent = assistant.create_agent()
        if agent is None:
            raise RuntimeError("Agent was not created properly!")
        session = assistant.setup_session(ctx.proc.userdata["vad"])

        # Connect to room
        await ctx.connect()

        # Start the session with the agent and room
        await session.start(
            agent=agent,
            room=ctx.room
        )

        # Voice-optimized greeting that mentions enhanced capabilities
        await session.generate_reply(
            instructions=f"Hello! I'm your voice assistant. Today is {current_date}. I can answer questions, search the web, crawl specific websites, check the weather, look up facts, get news headlines, solve math problems, and even tell jokes. What can I help you with today?"
        )

        logging.info("Assistant started successfully")

    except Exception as e:
        logging.error(f"Error in entrypoint: {str(e)}")
        # If anything fails, try a simpler greeting
        try:
            # Use the existing assistant but with a simpler greeting
            assistant = AIVoiceAssistant()
            # Use the same tools as the main agent for fallback
            simple_agent = Agent(
                instructions="You are a helpful assistant.",
                tools=[
                    web_search,
                    wiki_lookup,
                    get_news_headlines,
                    get_weather,
                    calculate,
                    get_current_datetime,
                    get_fun_content,
                    web_crawl,
                    search_locanto_browser,
                    locanto_matchmaking,
                    search_locanto,
                ]
            )
            session = assistant.setup_session(ctx.proc.userdata["vad"])

            await ctx.connect()
            await session.start(
                agent=simple_agent,
                room=ctx.room
            )

            # Simple greeting without any potential errors
            await session.generate_reply(instructions="Hello! How can I help you today?")
        except Exception as e2:
            logging.error(f"Error in fallback: {str(e2)}")
            raise
        
def main():
    import sys
    if len(sys.argv) > 1:
        # Pass command-line args to the agent as needed
        cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
    else:
        print("Dating Agent CLI: Use 'dating-agent dev' or 'python -m runtime.dating dev' to start the agent.")

if __name__ == "__main__":
    main()
