from __future__ import annotations

import os
import re
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from database import get_conn

MAX_PAGE_BYTES = 2_000_000
REQUEST_TIMEOUT = 15.0
POLITENESS_DELAY = 0.9
MAX_RESULT_PAGES = 15

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
CFEMAIL_RE = re.compile(r'data-cfemail="([0-9a-fA-F]+)"')

BLOCKED_DOMAINS = {
    "example.com", "example.org", "example.net", "yourdomain.com", "your-domain.com",
    "yourcompany.com", "mycompany.com", "yourbusiness.com", "yoursite.com",
    "mysite.com", "mywebsite.com", "yourname.com", "samples.com", "sample.com",
    "domain.com", "domain.net", "domain.org", "test.com", "test.org", "test.net",
    "email.com", "emails.com", "mail.com", "mailinator.com", "placeholder.com",
    "website.com", "website.org", "brand.com", "company.com", "sentry.io",
    "wixpress.com", "sentry-next.wixpress.com", "staticflickr.com", "shutterstock.com",
    "gettyimages.com", "adobestock.com", "istockphoto.com", "dreamstime.com",
    "cloudflare.com", "cloudflareinsights.com", "jquery.com", "googleapis.com",
    "google.com", "gstatic.com", "facebook.com", "twitter.com", "youtube.com",
    "instagram.com", "linkedin.com", "tiktok.com", "pinterest.com", "snapchat.com",
    "cdnjs.cloudflare.com", "bootstrapcdn.com", "fontawesome.com", "typekit.com",
    "doubleclick.net", "googletagmanager.com", "hotjar.com", "google-analytics.com",
    "tealium.com", "kissmetrics.com", "klaviyo.com", "mailchimp.com", "hubspot.com",
    "useloom.com", "calendly.com", "typeform.com", "disqus.com", "mailerlite.com",
    "vimeo.com", "dribbble.com", "behance.net", "medium.com", "wordpress.org",
    "w3.org", "schema.org", "mozilla.org", "apache.org", "opensource.org",
    "yandex.ru", "yahoo.com", "aol.com", "microsoft.com", "apple.com",
    "amazonaws.com", "vercel.app", "netlify.com", "surge.sh", "pages.dev",
    "github.com", "gitlab.com", "bitbucket.org", "npmjs.com", "sentry.link",
}

BLOCKED_LOCAL_PARTS = {
    "noreply", "no-reply", "donotreply", "do-not-reply", "noreply-mx",
    "no-reply-mail", "donotreply", "emailing", "dev-null", "null", "void",
    "root", "postmaster", "webmaster", "abuse", "unsubscribe", "info@no",
    "spam", "spamhaus", "test", "testing", "example", "sample", "fake",
    "dummy", "user", "username", "admin", "administrator",
}

PERSONAL_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
    "yahoo.com", "ymail.com", "icloud.com", "me.com", "mac.com", "protonmail.com",
    "proton.me", "aol.com", "zoho.com", "fastmail.com", "hey.com", "gmx.com",
    "mail.com", "protonmail.ch", "tutanota.com", "yandex.com",
}

GENERIC_LOCAL_PARTS = {
    "info", "contact", "support", "hello", "office", "admin", "reception",
    "inquiries", "inquiry", "enquiries", "enquiry", "bookings", "booking",
    "reservations", "sales", "billing", "accounts", "help", "mail", "email",
    "general", "inbox", "greetings", "welcome", "connect", "hallo",
    "careers", "jobs", "hiring", "hr", "recruiting", "recruitment", "team",
    "compliance", "privacy", "legal", "media", "press", "news", "marketing",
    "management", "customer", "customerservice", "service", "services",
    "frontdesk", "guest", "guests", "owners", "leasing", "maintenance",
    "notifications", "register", "registration", "orders", "order", "shop",
    "payments", "payment", "career", "job", "apply", "application",
}

PLATFORM_DOMAINS = {
    "placester.com", "realgeeks.com", "kvcore.com", "idxbroker.com",
    "chime.com", "loom.ly", "listingspark.com", "fiverealty.com",
    "rezora.com", "bftai.com", "flyhomes.com", "homelight.com",
    "highnote.io", "conceptlabs.io", "launchtools.com", "siteimprove.com",
}


def _load_env():
    candidates = [
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent / ".env",
    ]
    for path in candidates:
        if path.exists():
            load_dotenv(path)
            return


_load_env()


def openai_api_key():
    return os.getenv("OPENAI_API_KEY", "").strip()


def serper_api_key():
    return os.getenv("SERPER_API_KEY", "").strip()


def google_cse_keys():
    return os.getenv("GOOGLE_CSE_ID", "").strip(), os.getenv("GOOGLE_CSE_KEY", "").strip()


def tavily_api_key():
    return os.getenv("TAVILY_API_KEY", "").strip()


FREE_AI_DEFAULTS = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
    "openrouter": ("https://openrouter.ai/api/v1", "google/gemma-4-26b-a4b-it:free"),
}


def ai_config():
    provider = os.getenv("AI_PROVIDER", "openai").strip().lower() or "openai"
    if provider == "openai":
        key = openai_api_key()
    else:
        key = os.getenv("AI_API_KEY", "").strip()
    default_base, default_model = FREE_AI_DEFAULTS.get(provider, FREE_AI_DEFAULTS["openai"])
    base_url = os.getenv("AI_BASE_URL", "").strip() or default_base
    model = os.getenv("AI_MODEL", "").strip() or os.getenv("OPENAI_MODEL", "").strip() or default_model
    return provider, key, base_url, model


# ---------------------------------------------------------------- helpers

def normalize_email(email: str) -> str:
    email = email.strip().strip(".,;:<>[]()'\"").lower()
    return email


def is_plausible(email: str) -> bool:
    email = normalize_email(email)
    if not EMAIL_RE.fullmatch(email):
        return False
    local, _, domain = email.partition("@")
    domain = domain.lower()
    if domain in BLOCKED_DOMAINS or domain in PLATFORM_DOMAINS:
        return False
    if local.split("+")[0].lower() in BLOCKED_LOCAL_PARTS:
        return False
    if local.startswith("=") or ".." in local:
        return False
    if local == "info":
        return True
    return True


def deobfuscate(text: str) -> str:
    text = re.sub(r"&#64;|&#x40;|&commat;|&COMMAT;", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\[at\]\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(at\)\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+at\s+", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+\[dot\]\s+", ".", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\[dot\]\s*", ".", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(dot\)\s*", ".", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+dot\s+", ".", text, flags=re.IGNORECASE)
    return text


def decode_cfemail(hex_str: str):
    try:
        raw = bytes.fromhex(hex_str)
        key = raw[0]
        return "".join(chr(b ^ key) for b in raw[1:])
    except Exception:
        return None


# ---------------------------------------------------------------- fetch

def fetch_page(url: str, client: httpx.Client) -> str:
    resp = client.get(url, follow_redirects=True)
    resp.raise_for_status()
    content = resp.content
    if len(content) > MAX_PAGE_BYTES:
        content = content[:MAX_PAGE_BYTES]
    return content.decode("utf-8", errors="ignore")


def extract_emails(html: str) -> list[str]:
    emails: set[str] = set()

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if href.lower().startswith("mailto:"):
            candidate = normalize_email(href[len("mailto:"):].split("?", 1)[0])
            if candidate and is_plausible(candidate):
                emails.add(candidate)

    for match in CFEMAIL_RE.findall(html):
        decoded = decode_cfemail(match)
        if decoded and is_plausible(decoded):
            emails.add(normalize_email(decoded))

    text = deobfuscate(soup.get_text(" ", strip=True))
    for candidate in EMAIL_RE.findall(text):
        if is_plausible(candidate):
            emails.add(normalize_email(candidate))

    return sorted(emails)


def page_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    og = soup.find("meta", property="og:site_name")
    site = og.get("content", "").strip() if og else ""
    return (title or site)[:200]


def find_contact_url(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    best = None
    best_score = 0
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        label = " ".join(a.get_text(" ", strip=True).lower().split())
        score = 0
        lower = href.lower()
        for kw, s in (("contact", 5), ("reach", 4), ("team", 3), ("about", 2), ("email", 2), ("imprint", 3), ("impressum", 3)):
            if kw in lower or kw in label:
                score += s
        if score > best_score:
            try:
                full = urljoin(base_url, href)
            except Exception:
                continue
            if urlparse(full).netloc != urlparse(base_url).netloc:
                continue
            if full in seen:
                continue
            seen.add(full)
            if urlparse(full).path.lower().rstrip("/") in ("", "/index.html"):
                continue
            best, best_score = full, score
    return best


NON_CONTENT_EXT = (
    ".css", ".js", ".mjs", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".avif", ".ico", ".pdf", ".zip", ".gz", ".mp4", ".mp3", ".wav", ".woff",
    ".woff2", ".ttf", ".eot", ".xml", ".json", ".rss", ".txt", ".doc", ".docx",
    ".xls", ".xlsx", ".csv",
)
SKIP_PATH_PARTS = (
    "wp-content", "wp-json", "wp-includes", "feed", "login", "logout", "cart",
    "checkout", "account", "privacy-policy", "terms-of-service", "cookie-policy",
    "signup", "register", "download", "api/", "/cdn/", "cdn-cgi",
)


def internal_links(html: str, base_url: str, limit: int = 20) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    try:
        base_netloc = urlparse(base_url).netloc
    except Exception:
        return []
    candidates = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        try:
            full = urljoin(base_url, href)
            u = urlparse(full)
        except Exception:
            continue
        if u.netloc != base_netloc or u.scheme not in ("http", "https"):
            continue
        path = u.path.lower()
        if path.endswith(NON_CONTENT_EXT):
            continue
        if any(p in path for p in SKIP_PATH_PARTS):
            continue
        label = " ".join(a.get_text(" ", strip=True).lower().split())
        score = sum(
            s
            for kw, s in (
                ("contact", 6), ("team", 4), ("agent", 4), ("agents", 4),
                ("about", 2), ("email", 3), ("reach", 3), ("meet", 2),
                ("staff", 3), ("broker", 2), ("people", 2),
            )
            if kw in path or kw in label
        )
        if full in seen:
            continue
        seen.add(full)
        candidates.append((score, full))
    candidates.sort(key=lambda x: -x[0])
    return [full for _, full in candidates[:limit]]


def crawl_site(client: httpx.Client, base_url: str, max_internal: int = 4) -> list[tuple[str, str]]:
    """BFS crawl a site, preferring contact/team/agent pages, returning (url, html) pairs."""
    pages: list[tuple[str, str]] = []
    queue = [base_url]
    visited: set[str] = set()
    while queue and len(visited) < max_internal:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            html = fetch_page(url, client)
        except Exception:
            continue
        pages.append((url, html))
        for link in internal_links(html, url, limit=6):
            if link not in visited:
                queue.append(link)
        time.sleep(POLITENESS_DELAY)
    return pages


# ---------------------------------------------------------------- search

def build_queries(role: str, locations: list[str], country: str) -> list[str]:
    role = role.strip().strip('"')
    r = f'"{role}"'
    if country.upper().startswith("US"):
        country_name = "United States"
    elif country.upper().startswith("CA"):
        country_name = "Canada"
    elif country.upper().startswith("UK") or country.upper().startswith("GB"):
        country_name = "United Kingdom"
    elif country.upper().startswith("AU"):
        country_name = "Australia"
    elif country.upper().startswith("IE"):
        country_name = "Ireland"
    else:
        country_name = country

    queries: list[str] = []
    for loc in locations:
        loc = loc.strip()
        if not loc:
            continue

        # ---- General email discovery queries ----
        queries += [
            # Classic personal email patterns
            f'{r} "{loc}" "@gmail.com"',
            f'{r} "{loc}" "@gmail.com" OR "@outlook.com" OR "@yahoo.com" OR "@icloud.com"',
            f'{r} "{loc}" contact email',
            f'{r} "{loc}" email address',
            f'{r} in "{loc}" email',
            f'{r} "{loc}" {country_name} email list',
            # Contact/reach pages
            f'inurl:contact {r} "{loc}"',
            f'inurl:team {r} "{loc}"',
            f'inurl:about {r} "{loc}" email',
            f'inurl:agent {r} "{loc}" email',
            f'inurl:staff {r} "{loc}" email',
            f'inurl:directory {r} "{loc}"',
            # Email in anchor text / page
            f'{r} "{loc}" "contact us" email',
            f'{r} "{loc}" "reach us" email',
            f'{r} "{loc}" "email us"',
            f'{r} "{loc}" "send us an email"',
            # Listings with email field visible
            f'{r} "{loc}" "email:"',
            f'{r} "{loc}" "e-mail:"',
        ]

        # ---- Targeted directory/platform site: queries ----
        queries += [
            # Business directories
            f'site:yelp.com {r} "{loc}"',
            f'site:yellowpages.com {r} "{loc}"',
            f'site:manta.com {r} "{loc}"',
            f'site:chamberofcommerce.com {r} "{loc}"',
            f'site:bbb.org {r} "{loc}"',
            f'site:mapquest.com {r} "{loc}"',
            f'site:superpages.com {r} "{loc}"',
            f'site:whitepages.com {r} "{loc}"',
            f'site:foursquare.com {r} "{loc}"',
            f'site:hotfrog.us {r} "{loc}"',
            f'site:angieslist.com {r} "{loc}"',
            f'site:thumbtack.com {r} "{loc}"',
            # Real estate specific
            f'site:realtor.com {r} "{loc}"',
            f'site:zillow.com "{loc}" {r} email',
            f'site:trulia.com {r} "{loc}"',
            f'site:homes.com {r} "{loc}"',
            f'site:redfin.com agent "{loc}"',
            f'site:century21.com agent "{loc}"',
            f'site:coldwellbanker.com agent "{loc}"',
            f'site:remax.com agent "{loc}"',
            f'site:compass.com agent "{loc}"',
            f'site:bhgrealestate.com agent "{loc}"',
            f'site:sothebysrealty.com agent "{loc}"',
            # Professional networks / lead databases
            f'site:linkedin.com {r} "{loc}" email',
            f'site:zoominfo.com {r} "{loc}"',
            f'site:rocketreach.co {r} "{loc}"',
            f'site:spokeo.com {r} "{loc}"',
            f'site:intelius.com {r} "{loc}"',
            # Local / community sites
            f'site:alignable.com {r} "{loc}"',
            f'site:nextdoor.com {r} "{loc}"',
            f'site:craigslist.org {r} "{loc}" email',
            # Associations & license boards
            f'"{loc}" "{role}" association directory email',
            f'"{loc}" "{role}" board members contact email',
            f'"{loc}" "{role}" license directory contact',
            f'"{loc}" realtor association email directory',
        ]

    return queries


def search_serper(query: str, client: httpx.Client, page: int = 1) -> list[str]:
    resp = client.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": serper_api_key(), "Content-Type": "application/json"},
        json={"q": query, "gl": "us", "hl": "en", "num": 10, "page": page},
    )
    resp.raise_for_status()
    data = resp.json()
    urls = []
    for item in data.get("organic", [])[:10]:
        link = item.get("link") or item.get("url")
        if link:
            urls.append(link)
    return urls


def search_tavily(query: str, client: httpx.Client, page: int = 1) -> list[str]:
    """Returns list of URLs. Call search_tavily_full for snippet harvesting."""
    return [r["url"] for r in _tavily_results(query, client) if r.get("url")]


def _tavily_results(query: str, client: httpx.Client) -> list[dict]:
    headers = {"Authorization": f"Bearer {tavily_api_key()}", "Content-Type": "application/json"}
    payload = {
        "query": query,
        "max_results": 25,
        "search_depth": "advanced",
        "include_answer": False,
        "include_raw_content": False,
    }
    try:
        resp = client.post("https://api.tavily.com/search", headers=headers, json=payload, timeout=30.0)
    except Exception:
        resp = client.post(
            "https://api.tavily.com/search",
            headers={"Content-Type": "application/json"},
            json={**payload, "api_key": tavily_api_key()},
            timeout=30.0,
        )
    resp.raise_for_status()
    return resp.json().get("results", [])


def harvest_emails_from_tavily(query: str, client: httpx.Client) -> list[tuple[str, str, str]]:
    """Returns list of (email, url, title) harvested directly from Tavily snippets."""
    results = []
    try:
        for item in _tavily_results(query, client):
            url = item.get("url", "")
            title = item.get("title", "")
            content = item.get("content", "") or ""
            text = deobfuscate(content)
            for candidate in EMAIL_RE.findall(text):
                if is_plausible(candidate):
                    results.append((normalize_email(candidate), url, title))
    except Exception:
        pass
    return results


def search_google_cse(query: str, client: httpx.Client, page: int = 1) -> list[str]:
    cse_id, api_key = google_cse_keys()
    resp = client.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"key": api_key, "cx": cse_id, "q": query, "num": 10, "start": (page - 1) * 10 + 1},
    )
    resp.raise_for_status()
    data = resp.json()
    return [item.get("link") for item in data.get("items", []) if item.get("link")]


def search_duckduckgo(query: str, client: httpx.Client, page: int = 1) -> list[str]:
    resp = client.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query, "s": (page - 1) * 25},
        headers={"User-Agent": DEFAULT_HEADERS["User-Agent"]},
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    urls = []
    for a in soup.select("a.result__a"):
        href = a.get("href", "")
        if "uddg=" in href:
            from urllib.parse import unquote, parse_qs, urlparse as _up

            qs = parse_qs(_up(href).query)
            target = qs.get("uddg", [None])[0]
            if target:
                urls.append(unquote(target))
        elif href.startswith("http"):
            urls.append(href)
    return urls


def search_web(query: str, client: httpx.Client, page: int = 1) -> list[str]:
    if all(google_cse_keys()):
        try:
            return search_google_cse(query, client, page)
        except Exception:
            pass
    if tavily_api_key():
        try:
            return search_tavily(query, client, page)
        except Exception:
            pass
    if serper_api_key():
        try:
            return search_serper(query, client, page)
        except Exception:
            pass
    return search_duckduckgo(query, client, page)


# ---------------------------------------------------------------- OpenAI

def _openai_extract(raw: dict) -> dict:
    return {
        "email": normalize_email(raw.get("email", "")),
        "valid": bool(raw.get("valid")),
        "status": raw.get("status") or "invalid",
        "confidence": max(0.0, min(1.0, float(raw.get("confidence") or 0.0))),
        "name": raw.get("name") or None,
        "company": raw.get("company") or None,
    }


def validate_with_openai(entries: list[dict], role: str, location: str, progress_callback=None) -> list[dict]:
    provider, key, base_url, model = ai_config()
    if not key or not entries:
        return [_heuristic(entry) for entry in entries]
    endpoint = f"{base_url.rstrip('/')}/chat/completions"

    prompt = {
        "role": "system",
        "content": (
            "You are an expert email verification assistant for a professional lead-generation tool. "
            "You are given emails extracted from web pages (each with a source URL and page title) for "
            f"people matching the role \"{role}\" in the location \"{location}\". "
            "Identify which emails are REAL, usable contact emails for real people or real businesses, "
            "and reject junk (placeholders, framework/asset emails, tracker emails, clearly fake).\n"
            "Rules:\n"
            "- valid: true only if the email is real and usable.\n"
            "- status: 'personal' for an individual person's inbox (gmail/outlook/etc or name-based domain); "
            "'generic' for role mailboxes (info@, contact@, support@, office@, compliance@, bookings@, sales@, etc.); "
            "'invalid' for junk or irrelevant emails.\n"
            "- Mark emails from website-platforms/site-builders (e.g. @placester.com, @realgeeks.com), banks, "
            "or clearly unrelated businesses as 'invalid'.\n"
            "- confidence: 0.0-1.0 how confident you are it is a real, deliverable contact email.\n"
            "- name: if the page clearly shows the person's name, return it, otherwise null.\n"
            "- company: best guess of the business name from the domain and title, otherwise null.\n"
            "Return strict JSON: {\"results\":[{\"email\":\"...\",\"valid\":true,\"status\":\"personal\","
            "\"confidence\":0.9,\"name\":\"... or null\",\"company\":\"... or null\"}]}. "
            "Only include emails present in the input. Never fabricate emails."
        ),
    }

    chunk_size = 40
    chunks = [entries[i : i + chunk_size] for i in range(0, len(entries), chunk_size)]
    total_chunks = len(chunks)
    completed_chunks = 0
    results_lock = threading.Lock()
    results = []

    def _process_chunk(chunk: list[dict]) -> list[dict]:
        nonlocal completed_chunks
        chunk_results = []
        user_content = {
            "role": "user",
            "content": (
                "Here are the extracted emails in JSON:\n"
                + "\n".join(
                    f"- email: {e['email']} | source: {e.get('source_url', '')} | title: {e.get('page_title', '')}"
                    for e in chunk
                )
            ),
        }

        def _call(payload: dict):
            resp = httpx.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=45.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

        try:
            base_payload = {
                "model": model,
                "messages": [prompt, user_content],
                "temperature": 0,
            }
            try:
                content = _call({**base_payload, "response_format": {"type": "json_object"}})
            except Exception:
                content = _call(base_payload)

            import json
            import re as _re

            parsed = None
            try:
                parsed = json.loads(content)
            except Exception:
                m_json = _re.search(r"\{.*\}", content, _re.DOTALL)
                if m_json:
                    try:
                        parsed = json.loads(m_json.group(0))
                    except Exception:
                        parsed = None

            if isinstance(parsed, list):
                parsed = {"results": parsed}
            verdicts = (parsed or {}).get("results") or []
            covered = set()
            for raw in verdicts:
                entry = _openai_extract(raw)
                if entry["email"]:
                    chunk_results.append(entry)
                    covered.add(entry["email"])

            for e in chunk:
                if normalize_email(e["email"]) not in covered:
                    chunk_results.append(_heuristic(e))
        except Exception:
            chunk_results.extend(_heuristic(e) for e in chunk)

        with results_lock:
            completed_chunks += 1
            if progress_callback:
                progress_callback(completed_chunks, total_chunks)
        return chunk_results

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_process_chunk, c) for c in chunks]
        for f in futures:
            results.extend(f.result())

    return results


def _heuristic(entry: dict) -> dict:
    email = normalize_email(entry["email"])
    local, _, domain = email.partition("@")
    confidence = 0.5
    if entry.get("from_mailto"):
        confidence += 0.25
    if domain in PERSONAL_DOMAINS:
        status = "personal"
        confidence += 0.2
    elif local.lower() in GENERIC_LOCAL_PARTS:
        status = "generic"
    else:
        status = "personal"
    return {
        "email": email,
        "valid": True,
        "status": status,
        "confidence": round(min(1.0, confidence), 2),
        "name": entry.get("name"),
        "company": entry.get("company"),
    }


# ---------------------------------------------------------------- pipeline

def init_search(search_id: str, role: str, location: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO searches (id, role, location, status) VALUES (?, ?, ?, 'running')",
        (search_id, role, location),
    )
    conn.commit()
    conn.close()


def update_search(search_id: str, pages_checked: int = None, emails_found: int = None, status: str = None, message: str = None):
    conn = get_conn()
    sets, args = [], []
    if pages_checked is not None:
        sets.append("pages_checked = ?")
        args.append(pages_checked)
    if emails_found is not None:
        sets.append("emails_found = ?")
        args.append(emails_found)
    if status:
        sets.append("status = ?")
        args.append(status)
        if status in ("done", "failed"):
            sets.append("finished_at = datetime('now')")
    if message == "":
        sets.append("message = NULL")
    elif message is not None:
        sets.append("message = ?")
        args.append(message)
    if sets:
        args.append(search_id)
        conn.execute(f"UPDATE searches SET {', '.join(sets)} WHERE id = ?", args)
        conn.commit()
    conn.close()


def save_contacts(search_id: str, validated: list[dict], source_map: dict, personal_only: bool = True):
    conn = get_conn()
    for v in validated:
        if not v.get("valid"):
            continue
        if personal_only:
            # Keep only real personal inboxes on free providers (gmail/yahoo/outlook/etc.),
            # dropping role mailboxes (info@, office@) and name@company.com addresses.
            domain = v["email"].partition("@")[2].lower()
            if v.get("status") == "generic" or domain not in PERSONAL_DOMAINS:
                continue
        existing_this = conn.execute(
            "SELECT id FROM contacts WHERE search_id = ? AND email = ?", (search_id, v["email"])
        ).fetchone()
        if existing_this:
            continue
        # Check if this email was found in any other search (cross-search dedup)
        existing_other = conn.execute(
            "SELECT search_id FROM contacts WHERE email = ? AND search_id != ? LIMIT 1",
            (v["email"], search_id),
        ).fetchone()
        first_seen_search_id = existing_other["search_id"] if existing_other else None
        source = source_map.get(v["email"], {})
        conn.execute(
            "INSERT INTO contacts "
            "(search_id, email, name, company, role, location, source_url, confidence, status, first_seen_search_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                search_id,
                v["email"],
                v.get("name"),
                v.get("company"),
                v.get("role"),
                v.get("location"),
                source.get("source_url"),
                v.get("confidence"),
                v.get("status"),
                first_seen_search_id,
            ),
        )
    conn.commit()
    conn.close()


def is_search_stopped(search_id: str) -> bool:
    try:
        conn = get_conn()
        row = conn.execute("SELECT status FROM searches WHERE id = ?", (search_id,)).fetchone()
        conn.close()
        return bool(row and row["status"] in ("stopping", "stopped", "cancelled"))
    except Exception:
        return False


def run_search(search_id: str, role: str, location: str, country: str = "US", max_pages: int = 20, personal_only: bool = False):
    found: dict[str, dict] = {}
    pages_checked = 0
    source_map: dict[str, dict] = {}
    visited: set[str] = set()
    failed_urls: set[str] = set()   # Sites that errored — will be retried once

    try:
        if not any(google_cse_keys()) and not tavily_api_key() and not serper_api_key():
            update_search(
                search_id,
                status="failed",
                message=(
                    "No search backend configured. Add a free search key to your .env, then retry:\n"
                    "- TAVILY_API_KEY (no card needed): https://tavily.com/manage/keys\n"
                    "- GOOGLE_CSE_ID + GOOGLE_CSE_KEY (free 100/day): https://developers.google.com/custom-search/v1/overview"
                ),
            )
            return
        locations = [x.strip() for x in re.split(r"[,;\n]+", location) if x.strip()] or [location.strip()]
        queries = build_queries(role, locations, country)

        def _process_site(url: str, client: httpx.Client, retry: bool = False) -> None:
            """Crawl a site URL and harvest emails from all its pages."""
            nonlocal pages_checked
            timeout = REQUEST_TIMEOUT * 2 if retry else REQUEST_TIMEOUT
            try:
                site_pages = crawl_site(
                    httpx.Client(headers=DEFAULT_HEADERS, timeout=timeout, follow_redirects=True)
                    if retry else client,
                    url,
                    max_internal=8,
                )
            except Exception:
                if not retry:
                    failed_urls.add(url)
                return
            pages_checked += len(site_pages)
            site_title = ""
            for purl, phtml in site_pages:
                if not site_title:
                    site_title = page_title(phtml)
                for e in extract_emails(phtml):
                    if e not in found:
                        found[e] = {
                            "email": e,
                            "source_url": purl,
                            "page_title": site_title,
                            "from_mailto": False,
                        }
                        source_map[e] = {"source_url": purl}

        with httpx.Client(headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            for query in queries:
                if pages_checked >= max_pages or is_search_stopped(search_id):
                    break
                for page in range(1, MAX_RESULT_PAGES + 1):
                    if pages_checked >= max_pages or is_search_stopped(search_id):
                        break
                    try:
                        urls = search_web(query, client, page=page)
                    except Exception:
                        urls = []
                    if not urls:
                        break
                    for url in urls:
                        if pages_checked >= max_pages or is_search_stopped(search_id):
                            break
                        if url in visited:
                            continue
                        visited.add(url)
                        _process_site(url, client)
                        update_search(search_id, pages_checked=pages_checked, emails_found=len(found))
                        time.sleep(POLITENESS_DELAY)

                    # --- Harvest emails directly from Tavily snippets (catches directory listings) ---
                    if tavily_api_key() and not is_search_stopped(search_id):
                        try:
                            for (em, src_url, src_title) in harvest_emails_from_tavily(query, client):
                                if em not in found:
                                    found[em] = {
                                        "email": em,
                                        "source_url": src_url,
                                        "page_title": src_title,
                                        "from_mailto": False,
                                    }
                                    source_map[em] = {"source_url": src_url}
                            update_search(search_id, emails_found=len(found))
                        except Exception:
                            pass

            # --- Retry failed sites once with a longer timeout ---
            if failed_urls and not is_search_stopped(search_id):
                update_search(search_id, message=f"Retrying {len(failed_urls)} failed sites…")
                for url in list(failed_urls):
                    if pages_checked >= max_pages or is_search_stopped(search_id):
                        break
                    _process_site(url, client, retry=True)
                    update_search(search_id, pages_checked=pages_checked, emails_found=len(found))
                    time.sleep(POLITENESS_DELAY)
                update_search(search_id, message="")

        if is_search_stopped(search_id):
            # User cancelled early — save whatever found so far and mark stopped
            validated = [_heuristic(e) for e in found.values()]
            save_contacts(search_id, validated, source_map, personal_only=personal_only)
            update_search(search_id, status="stopped", message="Search stopped by user. Contacts saved.")
            return

        update_search(search_id, message=f"Verifying {len(found)} emails with AI...")
        def _on_progress(done_chunks, total_chunks):
            if not is_search_stopped(search_id):
                update_search(search_id, message=f"Verifying emails with AI ({done_chunks}/{total_chunks} batches)...")

        validated = validate_with_openai(list(found.values()), role, location, progress_callback=_on_progress)
        save_contacts(search_id, validated, source_map, personal_only=personal_only)

        final_status = "stopped" if is_search_stopped(search_id) else "done"
        update_search(search_id, status=final_status, emails_found=len(validated), message="")
    except Exception:
        update_search(search_id, status="failed")
        raise
