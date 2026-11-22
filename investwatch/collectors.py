"""Bounded collection of public pages and records from approved platform APIs."""

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import http.client
import ipaddress
import json
import re
import socket
from time import monotonic
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from pydantic import BaseModel, Field

AGENT = "InvestWatch"
USER_AGENT = AGENT + "/1.0 (+https://github.com/PiEtReK135/SWRI)"
MAX_RESPONSE = 2 * 1024 * 1024
TIKTOK_API = "https://open.tiktokapis.com"
SOCIAL_DOMAINS = {"facebook.com", "fb.com", "fb.watch", "instagram.com", "threads.net",
                  "tiktok.com", "tiktokcdn.com", "tiktokv.com", "youtube.com", "youtu.be",
                  "x.com", "twitter.com", "linkedin.com", "snapchat.com", "reddit.com"}


class CollectionError(Exception):
    def __init__(self, code, delay=None, status=None):
        super().__init__(code)
        self.code, self.delay = code, delay
        self.status = status


class WebSource(BaseModel):
    url: str = Field(max_length=2048)
    publisher: str = Field(min_length=1, max_length=250)
    link_prefix: str = Field(default="", max_length=256)
    pages: int = Field(default=4, ge=1, le=12)


class Settings(BaseModel):
    terms: list[str] = Field(default_factory=lambda: ["konto maklerskie", "inwestowanie", "doradztwo inwestycyjne"],
                             max_length=12)
    tiktok_creators: list[str] = Field(default_factory=list, max_length=20)
    tiktok_video_hosts: list[str] = Field(default_factory=list, max_length=30)
    websites: list[WebSource] = Field(default_factory=list, max_length=30)
    interval_minutes: int = Field(default=360, ge=30, le=10080)
    days: int = Field(default=30, ge=1, le=90)
    api_pages: int = Field(default=2, ge=1, le=5)
    meta_version: str = Field(default="v27.0", pattern=r"^v[0-9]{1,2}\.0$")
    scheduled: bool = False


@dataclass
class Material:
    source: str
    external_id: str
    kind: str
    url: str
    actor: str = ""
    title: str = ""
    blocks: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    published: str = ""
    label: str = ""
    payer: str = ""
    landing_url: str = ""
    market: str = ""
    profile_url: str = ""
    publisher_id: str = ""
    editorial_blocks: list[str] = field(default_factory=list)
    temporary_video_url: str = field(default="", repr=False)

    def data(self):
        data = asdict(self)
        data.pop("temporary_video_url")
        return data


def clean(value):
    return " ".join(str(value or "").split())


def safe_url(value):
    try:
        parsed = urlsplit(str(value or ""))
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.port not in (None, 443) or any(ord(char) < 33 for char in str(value))
                or len(str(value)) > 2048 or "\\" in parsed.netloc):
            return ""
        query = urlencode([(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True)
                           if key.lower() not in {"access_token", "token", "api_key", "signature"}
                           and not key.lower().startswith("utm_")])
        return urlunsplit(("https", parsed.hostname.lower(), parsed.path or "/", query, ""))
    except (ValueError, UnicodeError):
        return ""


def is_social(host):
    return any(host == domain or host.endswith("." + domain) for domain in SOCIAL_DOMAINS)


def public_address(host):
    addresses = list(dict.fromkeys(entry[4][0] for entry in socket.getaddrinfo(
        host, 443, type=socket.SOCK_STREAM)))
    if not addresses or any(not ip.is_global or ip.is_multicast for ip in map(ipaddress.ip_address, addresses)):
        raise CollectionError("PRIVATE_ADDRESS")
    return addresses[0]


def retry_seconds(value):
    if value.isdecimal() and len(value) < 9:
        return int(value)
    try:
        return max(0, round((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()))
    except (ValueError, TypeError, OverflowError):
        return None


def meta_failure(raw, status, delay):
    """Expose vendor error identifiers without storing payloads or credentials."""
    try:
        error = json.loads(raw).get("error") or {}
        code, subcode = error.get("code"), error.get("error_subcode")
    except (ValueError, AttributeError):
        return CollectionError(f"HTTP_{status}", delay, status)
    if type(code) is not int or not 0 < code < 10**8:
        return CollectionError(f"HTTP_{status}", delay, status)
    suffix = f"_{subcode}" if type(subcode) is int and 0 < subcode < 10**8 else ""
    if code in {4, 17, 32, 613}:
        status = 429
    return CollectionError(f"META_{code}{suffix}", delay, status)


def request(url, *, token=None, body=None, allow_missing=False, output=None):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.port not in (None, 443) or not parsed.hostname:
        raise CollectionError("UNSAFE_URL")
    address = public_address(parsed.hostname)
    connection = http.client.HTTPSConnection(parsed.hostname, timeout=12)
    # Keep the original host for TLS validation and pin the connection to the checked address.
    connection._create_connection = lambda target, timeout, source: socket.create_connection(
        (address, target[1]), timeout, source)
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        target = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        connection.request("POST" if body is not None else "GET", target,
                           json.dumps(body).encode() if body is not None else None, headers)
        response = connection.getresponse()
        if allow_missing and response.status in {404, 410}:
            return None, ""
        if response.status != 200:
            delay = retry_seconds(response.getheader("Retry-After", ""))
            if parsed.hostname == "graph.facebook.com" and token:
                try:
                    raw_error = response.read1(16384)
                except (OSError, http.client.HTTPException):
                    raw_error = b""
                raise meta_failure(raw_error, response.status, delay)
            raise CollectionError(f"HTTP_{response.status}", delay, response.status)
        content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
        if output is not None and content_type not in {"video/mp4", "application/octet-stream"}:
            raise CollectionError("UNSUPPORTED_MEDIA")
        deadline = monotonic() + (50 if output is not None else 15)
        limit = 150 * 1024 * 1024 if output is not None else MAX_RESPONSE
        chunks = []
        size = 0
        while chunk := response.read1(65536):
            size += len(chunk)
            if size > limit or monotonic() > deadline:
                raise CollectionError("RESPONSE_LIMIT")
            if output is None:
                chunks.append(chunk)
            else:
                output.write(chunk)
        return b"".join(chunks), response.getheader("Content-Type", "")
    finally:
        connection.close()


def api(url, query, token, body=None):
    payload, _ = request(url + "?" + urlencode(query), token=token, body=body)
    result = json.loads(payload)
    error = result.get("error") or {}
    if error and error.get("code") != "ok":
        raise CollectionError("API_REJECTED")
    return result


def download_tiktok_video(url, domains, output):
    if not safe_url(url) or urlsplit(url).hostname not in domains:
        raise CollectionError("MEDIA_HOST_NOT_CONFIGURED")
    request(url, output=output)


def date_label(value):
    value = str(value or "")
    if re.fullmatch(r"\d{8}", value):
        value = value[:4] + "-" + value[4:6] + "-" + value[6:]
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return ""


def meta_ads(term, settings, token):
    url = f"https://graph.facebook.com/{settings.meta_version}/ads_archive"
    query = {"ad_type": "ALL", "ad_active_status": "ALL", "ad_reached_countries": '["PL"]',
             "ad_delivery_date_min": (date.today() - timedelta(days=settings.days)).isoformat(),
             "search_terms": term, "limit": 25,
             "fields": ("id,page_id,page_name,ad_creative_bodies,ad_creative_link_titles,publisher_platforms,"
                        "ad_delivery_start_time")}
    for _ in range(settings.api_pages):
        reply = api(url, query, token)
        for item in reply.get("data", []):
            ident = str(item.get("id", ""))
            if not ident.isdecimal():
                continue
            titles = item.get("ad_creative_link_titles") or []
            title = titles[0] if titles else ""
            yield Material("META", ident, "PAID_AD", "https://www.facebook.com/ads/library/?id=" + ident,
                           actor=clean(item.get("page_name")), title=clean(title),
                           publisher_id=clean(item.get("page_id")),
                           blocks=list(map(clean, [*(item.get("ad_creative_bodies") or []), *titles])),
                           platforms=sorted(str(platform).upper() for platform in item.get("publisher_platforms") or []),
                           published=date_label(item.get("ad_delivery_start_time")), market="REACHED_PL")
        paging = reply.get("paging") or {}
        cursor = (paging.get("cursors") or {}).get("after")
        if not paging.get("next") or not cursor or cursor == query.get("after"):
            break
        query["after"] = cursor


def tiktok(kind, term, settings, token):
    dates = {"min": (date.today() - timedelta(days=settings.days)).strftime("%Y%m%d"),
             "max": date.today().strftime("%Y%m%d")}
    base = TIKTOK_API + "/v2/research/adlib/"
    if kind == "TIKTOK_ADS":
        path, key, fields = "ad/query/", "ads", "ad.id,ad.first_shown_date,advertiser.business_name"
        body = {"filters": {"ad_published_date_range": dates, "country_code_list": ["PL"]},
                "search_term": term, "search_type": "fuzzy_phrase", "max_count": 10}
    else:
        path, key, fields = "commercial_content/query/", "commercial_contents", "id,create_date,label,brand_names,creator,videos"
        filters = {"content_published_date_range": dates, "creator_country_code": "PL"}
        if settings.tiktok_creators:
            filters["creator_usernames"] = settings.tiktok_creators
        body = {"filters": filters, "max_count": 20}
    for _ in range(settings.api_pages):
        data = api(base + path, {"fields": fields}, token, body).get("data") or {}
        for item in data.get(key) or []:
            if kind == "TIKTOK_ADS":
                ad = item.get("ad") or {}
                ident = str(ad.get("id") or "")
                if not ident.isdecimal():
                    continue
                detail = api(base + "ad/detail/", {"fields": (
                    "ad.id,ad.title,ad.external_url,ad.call_to_action,advertiser.business_name,"
                    "advertiser.business_id,advertiser.paid_for_by,advertiser.profile_url"
                    + (",ad.videos" if settings.tiktok_video_hosts else ""))}, token,
                    {"ad_id": int(ident)}).get("data") or {}
                creative = detail.get("ad") or {}
                advertiser = detail.get("advertiser") or item.get("advertiser") or {}
                title = clean(creative.get("title"))
                video = next((entry.get("url") for entry in creative.get("videos") or []
                              if safe_url(entry.get("url")) and
                              urlsplit(entry["url"]).hostname in settings.tiktok_video_hosts), "")
                yield Material("TIKTOK", ident, "PAID_AD", "https://library.tiktok.com/ads/detail/?ad_id=" + ident,
                               actor=clean(advertiser.get("business_name")), title=title,
                               blocks=[title, clean(creative.get("call_to_action"))], platforms=["TIKTOK"],
                               published=date_label(ad.get("first_shown_date")), payer=clean(advertiser.get("paid_for_by")),
                               profile_url=safe_url(advertiser.get("profile_url")),
                               publisher_id=clean(advertiser.get("business_id")),
                               landing_url=safe_url(creative.get("external_url")), market="REACHED_PL",
                               temporary_video_url=video)
            else:
                ident = clean(item.get("id"))
                actor = clean((item.get("creator") or {}).get("username"))
                for index, video in enumerate(item.get("videos") or []):
                    url = safe_url(video.get("url"))
                    if not ident or urlsplit(url).hostname not in {"www.tiktok.com", "tiktok.com"}:
                        continue
                    yield Material("TIKTOK", f"{ident}/{index}", "DISCLOSED_POST", url, actor=actor,
                                   companies=list(map(clean, item.get("brand_names") or [])), platforms=["TIKTOK"],
                                   published=date_label(item.get("create_date")), label=clean(item.get("label")),
                                   market="CREATOR_PL")
        cursor = data.get("search_id")
        if str(data.get("has_more")).lower() != "true" or not cursor or cursor == body.get("search_id"):
            break
        body["search_id"] = cursor


class Page(HTMLParser):
    IGNORED = {"script", "style", "noscript", "template", "svg"}
    BLOCKS = {"title", "p", "div", "article", "section", "main", "li", "td", "th", "br", "h1", "h2", "h3", "h4"}
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.blocks, self.links, self.buffer = [], [], [], []
        self.editorial, self.main, self.chrome = [], [], []
        self.in_main = False
        self.title = ""
        self.in_title = False

    def flush(self):
        text = clean("".join(self.buffer))
        if self.in_title:
            self.title = text
        elif text:
            self.blocks.append(text)
            if not self.chrome:
                self.editorial.append(text)
                if self.in_main:
                    self.main.append(text)
        self.buffer.clear()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = (tag in self.IGNORED or "hidden" in attrs or attrs.get("aria-hidden") == "true"
                  or bool(re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", attrs.get("style") or "", re.I)))
        if self.stack:
            if tag not in self.VOID:
                self.stack.append(tag)
            return
        if hidden:
            self.flush()
            if tag not in self.VOID:
                self.stack.append(tag)
            return
        if tag in self.BLOCKS or tag in {"nav", "header", "footer"}:
            self.flush()
        if tag in {"nav", "header", "footer"}:
            self.chrome.append(tag)
        if tag == "main":
            self.in_main = True
        if tag == "title":
            self.in_title = True
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.stack:
            if tag in self.stack:
                index = len(self.stack) - 1 - self.stack[::-1].index(tag)
                del self.stack[index:]
            return
        if tag in self.BLOCKS or tag in {"nav", "header", "footer"}:
            self.flush()
        if self.chrome and self.chrome[-1] == tag:
            self.chrome.pop()
        if tag == "main":
            self.in_main = False
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if not self.stack:
            self.buffer.append(data)


def websites(config, stop):
    url = safe_url(config.url)
    host = urlsplit(url).hostname
    if not host or is_social(host):
        raise CollectionError("WEB_HOST_NOT_ALLOWED")
    origin = "https://" + host
    raw, _ = request(origin + "/robots.txt", allow_missing=True)
    robots = RobotFileParser()
    robots.parse(raw.decode("utf-8", errors="replace").splitlines() if raw else [])
    rate = robots.request_rate(AGENT)
    delay = max(1, robots.crawl_delay(AGENT) or 0, rate.seconds / rate.requests if rate and rate.requests else 0)
    if delay > 30:
        raise CollectionError("ROBOTS_DELAY", round(delay))
    queued, seen = [url], set()
    for _ in range(config.pages):
        if not queued or stop.wait(delay):
            return
        current = queued.pop(0)
        seen.add(current)
        if not robots.can_fetch(AGENT, current):
            if current == url:
                raise CollectionError("ROBOTS_DENIED")
            continue
        raw, content_type = request(current)
        if "text/html" not in content_type.lower():
            raise CollectionError("NOT_HTML")
        charset = re.search(r"charset=([a-z0-9_-]+)", content_type, re.I)
        page = Page()
        try:
            page.feed(raw.decode(charset[1] if charset else "utf-8", errors="replace"))
        except LookupError:
            page.feed(raw.decode("utf-8", errors="replace"))
        page.close()
        page.flush()
        yield Material("WEB", current, "WEB_PAGE", current, actor=config.publisher, title=page.title,
                       blocks=list(dict.fromkeys(page.blocks)), profile_url=origin + "/",
                       editorial_blocks=list(dict.fromkeys(page.main or page.editorial)))
        if config.link_prefix.startswith("/"):
            for link in page.links:
                target = safe_url(urljoin(current, link))
                parsed = urlsplit(target)
                if (parsed.hostname == host and not parsed.query and parsed.path.startswith(config.link_prefix)
                        and not re.search(r"\.(?:pdf|png|jpg|zip|mp4|xml)$", parsed.path, re.I)
                        and target not in seen and target not in queued and len(queued) < config.pages):
                    queued.append(target)
