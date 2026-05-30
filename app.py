import re
from datetime import date, timedelta

import requests
import streamlit as st

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
WIKIVOYAGE_API = "https://en.wikivoyage.org/w/api.php"
USER_AGENT = "TouristAttractionsApp/1.0 (https://github.com/arpitg18/telecom-churn)"
REQUEST_TIMEOUT = 30
OVERPASS_TIMEOUT = 60

PRICE_TABLE = {
    "theme_park": "$60",
    "water_park": "$45",
    "amusement_arcade": "$30",
    "aquarium": "$30",
    "zoo": "$25",
    "aerialway_station": "$40",
    "museum": "$15",
    "gallery": "$12",
    "castle": "$15",
    "archaeological_site": "$10",
    "attraction": "$10",
    "ruins": "$8",
    "monument": "$5",
    "alpine_hut": "$0",
    "place_of_worship": "Free / donation",
    "memorial": "Free",
    "artwork": "Free",
    "viewpoint": "Free",
    "picnic_site": "Free",
    "park": "Free",
    "garden": "Free",
    "nature_reserve": "Free",
    "beach": "Free",
    "peak": "Free",
    "volcano": "Free",
    "cave_entrance": "$8",
    "cliff": "Free",
    "ridge": "Free",
    "mountain_range": "Free",
    "glacier": "Free",
    "saddle": "Free",
    "bay": "Free",
    "hot_spring": "$10",
    "region": "Free",
    "locality": "Free",
    "island": "Free",
    "peninsula": "Free",
    "village": "Free",
}
DEFAULT_PRICE = "$10"

CATEGORY_KEYS = ("tourism", "historic", "leisure", "amenity", "natural", "aerialway", "place")

SORT_OPTIONS = [
    "Most famous",
    "Cheapest first",
    "Most expensive first",
    "Alphabetical",
]

WIKIVOYAGE_LISTING_TEMPLATES = ("see", "do", "view", "listing", "marker")
WIKIVOYAGE_MAX_SUBPAGES = 30
WIKIVOYAGE_MAX_LISTINGS = 120


@st.cache_data(ttl=3600, show_spinner=False)
def geocode_location(name: str):
    try:
        resp = requests.get(
            GEOCODE_URL,
            params={"name": name, "count": 1, "language": "en", "format": "json"},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        st.error(f"Geocoding network error: {e}")
        return None
    if not resp.ok:
        st.error(f"Geocoding error: HTTP {resp.status_code}")
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    results = (data or {}).get("results") or []
    if not results:
        return None
    item = results[0]
    parts = [item.get("name"), item.get("admin1"), item.get("country")]
    display_name = ", ".join(p for p in parts if p)
    return {
        "lat": float(item["latitude"]),
        "lon": float(item["longitude"]),
        "display_name": display_name or name,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_attractions(lat: float, lon: float, radius_m: int, limit: int):
    tourism_re = "museum|attraction|gallery|theme_park|water_park|zoo|aquarium|viewpoint|artwork|picnic_site|alpine_hut"
    historic_re = "monument|memorial|castle|ruins|archaeological_site"
    leisure_re = "park|garden|nature_reserve"
    amenity_re = "place_of_worship"
    natural_re = "beach|peak|volcano|cave_entrance|cliff|ridge|glacier|saddle|bay|hot_spring|mountain_range"
    aerialway_re = "station"
    place_re = "region|locality|island|peninsula|village"

    query = f"""
    [out:json][timeout:{OVERPASS_TIMEOUT}];
    (
      node["tourism"~"^({tourism_re})$"]["name"](around:{radius_m},{lat},{lon});
      way["tourism"~"^({tourism_re})$"]["name"](around:{radius_m},{lat},{lon});
      relation["tourism"~"^({tourism_re})$"]["name"](around:{radius_m},{lat},{lon});
      node["historic"~"^({historic_re})$"]["name"](around:{radius_m},{lat},{lon});
      way["historic"~"^({historic_re})$"]["name"](around:{radius_m},{lat},{lon});
      relation["historic"~"^({historic_re})$"]["name"](around:{radius_m},{lat},{lon});
      node["leisure"~"^({leisure_re})$"]["name"](around:{radius_m},{lat},{lon});
      way["leisure"~"^({leisure_re})$"]["name"](around:{radius_m},{lat},{lon});
      node["amenity"~"^({amenity_re})$"]["name"](around:{radius_m},{lat},{lon});
      way["amenity"~"^({amenity_re})$"]["name"](around:{radius_m},{lat},{lon});
      node["natural"~"^({natural_re})$"]["name"](around:{radius_m},{lat},{lon});
      way["natural"~"^({natural_re})$"]["name"]["wikipedia"](around:{radius_m},{lat},{lon});
      way["natural"~"^({natural_re})$"]["name"]["wikidata"](around:{radius_m},{lat},{lon});
      relation["natural"~"^({natural_re})$"]["name"](around:{radius_m},{lat},{lon});
      node["aerialway"~"^({aerialway_re})$"]["name"](around:{radius_m},{lat},{lon});
      node["place"~"^({place_re})$"]["name"]["wikipedia"](around:{radius_m},{lat},{lon});
      node["place"~"^({place_re})$"]["name"]["wikidata"](around:{radius_m},{lat},{lon});
      way["place"~"^({place_re})$"]["name"]["wikipedia"](around:{radius_m},{lat},{lon});
      way["place"~"^({place_re})$"]["name"]["wikidata"](around:{radius_m},{lat},{lon});
      relation["place"~"^({place_re})$"]["name"]["wikipedia"](around:{radius_m},{lat},{lon});
      relation["place"~"^({place_re})$"]["name"]["wikidata"](around:{radius_m},{lat},{lon});
    );
    out center body {limit * 10};
    """
    resp = None
    last_status = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            resp = requests.post(
                endpoint,
                data={"data": query},
                headers={"User-Agent": USER_AGENT},
                timeout=OVERPASS_TIMEOUT + 10,
            )
        except requests.RequestException:
            resp = None
            continue
        if resp.ok:
            break
        last_status = resp.status_code
        resp = None

    if resp is None:
        detail = f"HTTP {last_status}" if last_status else "no response"
        raise RuntimeError(
            f"All Overpass mirrors failed ({detail}). The OpenStreetMap "
            "servers are likely overloaded — try again in a moment."
        )
    try:
        elements = resp.json().get("elements", [])
    except ValueError:
        raise RuntimeError("Overpass returned an invalid response — try again in a moment.")

    by_name = {}
    for el in elements:
        tags = el.get("tags") or {}
        name = tags.get("name:en") or tags.get("name")
        if not name:
            continue
        existing = by_name.get(name)
        if existing is None:
            by_name[name] = el
            continue
        ex_tags = existing.get("tags") or {}
        has_wiki_new = bool(tags.get("wikipedia") or tags.get("wikidata"))
        has_wiki_old = bool(ex_tags.get("wikipedia") or ex_tags.get("wikidata"))
        if has_wiki_new and not has_wiki_old:
            by_name[name] = el
    return list(by_name.values())


def _find_templates(wikitext: str, template_names: tuple) -> list:
    results = []
    i = 0
    n = len(wikitext)
    while i < n - 1:
        if wikitext[i : i + 2] != "{{":
            i += 1
            continue
        j = i + 2
        while j < n and wikitext[j] in " \t\n":
            j += 1
        name_start = j
        while j < n and wikitext[j] not in "|}{ \t\n":
            j += 1
        tmpl_name = wikitext[name_start:j].lower().strip()
        if tmpl_name not in template_names:
            i += 1
            continue
        depth = 1
        k = j
        while k < n and depth > 0:
            if wikitext[k : k + 2] == "{{":
                depth += 1
                k += 2
            elif wikitext[k : k + 2] == "}}":
                depth -= 1
                k += 2
            else:
                k += 1
        if depth != 0:
            break
        body = wikitext[j : k - 2]
        results.append((tmpl_name, body))
        i = k
    return results


def _parse_template_fields(body: str) -> dict:
    parts = []
    current = []
    depth_square = 0
    depth_curly = 0
    i = 0
    while i < len(body):
        if body[i : i + 2] == "[[":
            depth_square += 1
            current.append(body[i : i + 2])
            i += 2
        elif body[i : i + 2] == "]]":
            depth_square -= 1
            current.append(body[i : i + 2])
            i += 2
        elif body[i : i + 2] == "{{":
            depth_curly += 1
            current.append(body[i : i + 2])
            i += 2
        elif body[i : i + 2] == "}}":
            depth_curly -= 1
            current.append(body[i : i + 2])
            i += 2
        elif body[i] == "|" and depth_square == 0 and depth_curly == 0:
            parts.append("".join(current))
            current = []
            i += 1
        else:
            current.append(body[i])
            i += 1
    parts.append("".join(current))

    fields = {}
    for part in parts:
        if "=" in part:
            key, _, val = part.partition("=")
            fields[key.strip().lower()] = val.strip()
    return fields


def _strip_wikitext(text: str) -> str:
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"'''([^']+)'''", r"\1", text)
    text = re.sub(r"''([^']+)''", r"\1", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    return text.strip()


def _parse_float(s):
    if not s:
        return None
    s = s.strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _wikivoyage_fetch_wikitext(page: str):
    try:
        resp = requests.get(
            WIKIVOYAGE_API,
            params={
                "action": "parse",
                "page": page,
                "prop": "wikitext",
                "format": "json",
                "redirects": 1,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return None, None
    if not resp.ok:
        return None, None
    try:
        data = resp.json()
    except ValueError:
        return None, None
    parse = data.get("parse")
    if not parse:
        return None, None
    title = parse.get("title")
    wikitext = (parse.get("wikitext") or {}).get("*")
    return title, wikitext


def _wikivoyage_search_page(query: str):
    try:
        resp = requests.get(
            WIKIVOYAGE_API,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": 1,
                "format": "json",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return None
    if not resp.ok:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    results = data.get("query", {}).get("search", [])
    if not results:
        return None
    return results[0].get("title")


def _wikivoyage_list_subpages(title: str) -> list:
    try:
        resp = requests.get(
            WIKIVOYAGE_API,
            params={
                "action": "query",
                "list": "allpages",
                "apprefix": f"{title}/",
                "apnamespace": 0,
                "aplimit": 50,
                "format": "json",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return []
    if not resp.ok:
        return []
    try:
        data = resp.json()
    except ValueError:
        return []
    return [p["title"] for p in data.get("query", {}).get("allpages", []) if "title" in p]


def _wikivoyage_fetch_multi_wikitext(titles: list) -> dict:
    if not titles:
        return {}
    out = {}
    for chunk_start in range(0, len(titles), 50):
        chunk = titles[chunk_start : chunk_start + 50]
        try:
            resp = requests.get(
                WIKIVOYAGE_API,
                params={
                    "action": "query",
                    "prop": "revisions",
                    "rvprop": "content",
                    "rvslots": "main",
                    "titles": "|".join(chunk),
                    "format": "json",
                    "redirects": 1,
                },
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException:
            continue
        if not resp.ok:
            continue
        try:
            data = resp.json()
        except ValueError:
            continue
        for _, page in data.get("query", {}).get("pages", {}).items():
            if page.get("missing") is not None:
                continue
            revisions = page.get("revisions", [])
            if not revisions:
                continue
            rev = revisions[0]
            content = (
                (rev.get("slots", {}) or {}).get("main", {}).get("*")
                or rev.get("*")
                or ""
            )
            if content:
                out[page.get("title", "")] = content
    return out


def _parse_listings_from_wikitext(wikitext: str, seen_names: set, source_page: str = "") -> list:
    listings = []
    for tmpl_name, body in _find_templates(wikitext, WIKIVOYAGE_LISTING_TEMPLATES):
        fields = _parse_template_fields(body)
        ltype = (fields.get("type") or tmpl_name).lower()
        if ltype not in ("see", "do", "view"):
            continue
        name = _strip_wikitext(fields.get("name", ""))
        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        listings.append({
            "name": name,
            "lat": _parse_float(fields.get("lat")),
            "lon": _parse_float(fields.get("long") or fields.get("lon")),
            "url": fields.get("url", "").strip(),
            "price": _strip_wikitext(fields.get("price", "")),
            "content": _strip_wikitext(fields.get("content", "")),
            "image": fields.get("image", "").strip(),
            "wikidata": fields.get("wikidata", "").strip(),
            "type": ltype,
            "source_page": source_page,
        })
    return listings


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_wikivoyage_listings(location: str) -> list:
    title, wikitext = _wikivoyage_fetch_wikitext(location)
    if not wikitext:
        found = _wikivoyage_search_page(location)
        if not found:
            return []
        title, wikitext = _wikivoyage_fetch_wikitext(found)
        if not wikitext:
            return []

    seen_names = set()
    listings = _parse_listings_from_wikitext(wikitext, seen_names, source_page=title or location)

    if title:
        subpages = _wikivoyage_list_subpages(title)[:WIKIVOYAGE_MAX_SUBPAGES]
        if subpages:
            sub_wikitexts = _wikivoyage_fetch_multi_wikitext(subpages)
            for sub_title, sub_wikitext in sub_wikitexts.items():
                listings.extend(
                    _parse_listings_from_wikitext(sub_wikitext, seen_names, source_page=sub_title)
                )

    if len(listings) > WIKIVOYAGE_MAX_LISTINGS:
        listings.sort(key=lambda l: (0 if l.get("wikidata") else 1,))
        listings = listings[:WIKIVOYAGE_MAX_LISTINGS]
    return listings


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_wikipedia_summary(wikipedia_tag: str):
    if not wikipedia_tag or ":" not in wikipedia_tag:
        return None
    lang, title = wikipedia_tag.split(":", 1)
    lang = lang.strip() or "en"
    title = title.strip().replace(" ", "_")
    if not title:
        return None
    try:
        resp = requests.get(
            f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}",
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return None
    if not resp.ok:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    return {
        "extract": data.get("extract", ""),
        "thumbnail": (data.get("thumbnail") or {}).get("source"),
    }


@st.cache_data(ttl=86400, show_spinner=False)
def wikidata_to_wikipedia(qid: str):
    if not qid or not qid.startswith("Q"):
        return None
    try:
        resp = requests.get(
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbgetentities",
                "ids": qid,
                "props": "sitelinks",
                "format": "json",
                "sitefilter": "enwiki",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return None
    if not resp.ok:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    title = (
        data.get("entities", {})
        .get(qid, {})
        .get("sitelinks", {})
        .get("enwiki", {})
        .get("title")
    )
    return f"en:{title}" if title else None


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_pageviews(wikipedia_tag: str) -> int:
    if not wikipedia_tag or ":" not in wikipedia_tag:
        return 0
    lang, title = wikipedia_tag.split(":", 1)
    lang = lang.strip() or "en"
    title = title.strip().replace(" ", "_")
    if not title:
        return 0
    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=30)
    url = (
        f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"{lang}.wikipedia/all-access/user/{title}/daily/"
        f"{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}"
    )
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return 0
    if not resp.ok:
        return 0
    try:
        items = resp.json().get("items", [])
    except ValueError:
        return 0
    return sum(item.get("views", 0) for item in items)


def get_price_estimate(tags: dict) -> str:
    aerialway = tags.get("aerialway")
    if aerialway == "station":
        return PRICE_TABLE["aerialway_station"]
    for key in CATEGORY_KEYS:
        v = tags.get(key)
        if v and v in PRICE_TABLE:
            return PRICE_TABLE[v]
    return DEFAULT_PRICE


def price_numeric(price_str: str) -> int:
    if not price_str:
        return 0
    if "free" in price_str.lower():
        return 0
    m = re.search(r"\d+", price_str)
    return int(m.group()) if m else 0


def category_label(tags: dict) -> str:
    if tags.get("aerialway") == "station":
        return "Cable Car Station"
    for key in CATEGORY_KEYS:
        v = tags.get(key)
        if v:
            return v.replace("_", " ").title()
    return "Attraction"


def get_coords(element: dict):
    if "lat" in element and "lon" in element:
        return element["lat"], element["lon"]
    center = element.get("center") or {}
    if "lat" in center and "lon" in center:
        return center["lat"], center["lon"]
    return None, None


def _truncate(text: str, max_len: int = 280) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rsplit(" ", 1)[0] + "…"


def enrich_osm(element: dict) -> dict:
    tags = element.get("tags") or {}
    wiki_tag = tags.get("wikipedia")
    if not wiki_tag and tags.get("wikidata"):
        wiki_tag = wikidata_to_wikipedia(tags["wikidata"])
    summary = fetch_wikipedia_summary(wiki_tag) if wiki_tag else None
    pageviews = fetch_pageviews(wiki_tag) if wiki_tag else 0
    name = tags.get("name:en") or tags.get("name") or "Unnamed attraction"
    return {
        "element": element,
        "tags": tags,
        "name": name,
        "summary": summary,
        "pageviews": pageviews,
        "price_str": get_price_estimate(tags),
        "source": "OpenStreetMap",
        "category": category_label(tags),
    }


def enrich_wikivoyage(listing: dict) -> dict:
    name = listing["name"]
    wiki_tag = None
    if listing.get("wikidata"):
        wiki_tag = wikidata_to_wikipedia(listing["wikidata"])
    if not wiki_tag:
        wiki_tag = f"en:{name}"
    summary = fetch_wikipedia_summary(wiki_tag)
    if not summary or not summary.get("extract"):
        summary = {"extract": listing.get("content", ""), "thumbnail": None}
    elif listing.get("content") and not summary.get("extract"):
        summary["extract"] = listing["content"]

    pageviews = fetch_pageviews(wiki_tag) if wiki_tag else 0
    if pageviews == 0 and listing.get("wikidata"):
        resolved = wikidata_to_wikipedia(listing["wikidata"])
        if resolved:
            pageviews = fetch_pageviews(resolved)

    price = listing.get("price") or ""
    if not price:
        price = DEFAULT_PRICE

    coords_present = listing.get("lat") is not None and listing.get("lon") is not None
    element = {"tags": {"name": name}}
    if coords_present:
        element["lat"] = listing["lat"]
        element["lon"] = listing["lon"]

    return {
        "element": element,
        "tags": {"name": name},
        "name": name,
        "summary": summary,
        "pageviews": pageviews,
        "price_str": price,
        "source": "Wikivoyage",
        "category": listing.get("type", "see").capitalize(),
        "url": listing.get("url", ""),
    }


def sort_enriched(items: list, sort_by: str) -> list:
    if sort_by == "Most famous":
        return sorted(
            items,
            key=lambda i: (
                0 if i.get("source") == "Wikivoyage" else 1,
                -i["pageviews"],
                i["name"].lower(),
            ),
        )
    if sort_by == "Cheapest first":
        return sorted(items, key=lambda i: (price_numeric(i["price_str"]), i["name"].lower()))
    if sort_by == "Most expensive first":
        return sorted(items, key=lambda i: (-price_numeric(i["price_str"]), i["name"].lower()))
    return sorted(items, key=lambda i: i["name"].lower())


def render_attraction_card(item: dict) -> None:
    name = item["name"]
    lat, lon = get_coords(item["element"])
    label = item.get("category", "Attraction")
    price = item["price_str"]
    summary = item["summary"] or {}
    image = summary.get("thumbnail")
    description = summary.get("extract")
    pageviews = item["pageviews"]
    source = item.get("source", "")
    url = item.get("url", "")

    with st.container(border=True):
        if image:
            st.image(image, use_container_width=True)
        st.subheader(name)
        st.caption(f"{label} · {source}" if source else label)
        if description:
            st.write(_truncate(description))
        st.markdown(f"**Estimated price:** {price}")
        if pageviews:
            st.caption(f"~{pageviews:,} Wikipedia views (last 30 days)")
        links = []
        if url:
            links.append(f"[Official site]({url})")
        if lat is not None and lon is not None:
            links.append(
                f"[View on map](https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon})"
            )
        if links:
            st.markdown(" · ".join(links))


def main() -> None:
    st.set_page_config(page_title="Top Tourist Attractions", page_icon="\U0001f5fa️", layout="wide")
    st.title("\U0001f5fa️ Top Tourist Attractions")
    st.caption("Pick a city, state, or country and see top activities with estimated prices.")

    with st.sidebar:
        st.markdown("### Search")
        location = st.text_input("City / state / country", value="Lucerne")
        radius_km = st.number_input("Search radius (km)", min_value=1, max_value=100, value=30)
        limit = st.number_input("Max results", min_value=5, max_value=100, value=30)
        sort_by = st.selectbox("Sort by", SORT_OPTIONS, index=0)
        name_filter = st.text_input("Filter by name (optional)")
        search = st.button("Search", type="primary", use_container_width=True)
        if st.button("\U0001f504 Clear cache & refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Data sources: [Wikivoyage](https://wikivoyage.org) (curated 'See/Do' lists per destination) "
        "+ [OpenStreetMap](https://openstreetmap.org) (broader coverage) "
        "+ [Wikipedia](https://wikipedia.org) (descriptions, popularity). "
        "Prices come from Wikivoyage when listed; otherwise static estimates by category. "
        "No API key required."
    )

    if not search:
        st.info("Enter a location in the sidebar and tap **Search** to begin.")
        return

    if not location.strip():
        st.warning("Please enter a location.")
        return

    with st.spinner(f"Looking up '{location}'…"):
        geo = geocode_location(location.strip())

    if not geo:
        st.error("Location not found — try a different spelling or a more specific name.")
        return

    st.subheader(f"\U0001f4cd {geo['display_name']}")
    st.caption(f"Coordinates: {geo['lat']:.4f}, {geo['lon']:.4f}")

    with st.spinner("Fetching curated attractions from Wikivoyage…"):
        wv_listings = fetch_wikivoyage_listings(location.strip())

    try:
        with st.spinner("Fetching attractions from OpenStreetMap…"):
            osm_elements = fetch_attractions(
                geo["lat"], geo["lon"], int(radius_km) * 1000, int(limit)
            )
    except RuntimeError as e:
        st.error(str(e))
        osm_elements = []

    if not wv_listings and not osm_elements:
        st.info("No attractions found — try widening the radius or a different location.")
        return

    with st.spinner(f"Looking up popularity and details… (cached after first run)"):
        wv_items = [enrich_wikivoyage(l) for l in wv_listings]
        osm_items = [enrich_osm(el) for el in osm_elements]

    seen = {i["name"].lower() for i in wv_items}
    merged = list(wv_items)
    for item in osm_items:
        if item["name"].lower() not in seen:
            merged.append(item)
            seen.add(item["name"].lower())

    filter_text = name_filter.strip().lower()
    if filter_text:
        filtered = [i for i in merged if filter_text in i["name"].lower()]
    else:
        filtered = merged

    sorted_items = sort_enriched(filtered, sort_by)
    if not filter_text:
        sorted_items = sorted_items[: int(limit)]

    with st.expander(f"\U0001f50d Diagnostics — Wikivoyage: {len(wv_items)}, OSM: {len(osm_items)}, total merged: {len(merged)}"):
        st.write(f"Resolved location: **{geo['display_name']}** at `{geo['lat']:.5f}, {geo['lon']:.5f}`")
        if filter_text:
            st.write(f"Matching filter `{name_filter}`: **{len(filtered)}**")
        if wv_listings:
            pages_seen = sorted({l.get("source_page", "") for l in wv_listings if l.get("source_page")})
            if pages_seen:
                st.write(f"Wikivoyage pages parsed ({len(pages_seen)}):")
                st.write(", ".join(pages_seen))
        if wv_items:
            st.write("Wikivoyage curated names:")
            st.write(", ".join(sorted(i["name"] for i in wv_items)))
        if osm_items:
            st.write("OpenStreetMap names (excluding ones already in Wikivoyage):")
            wv_names = {i["name"].lower() for i in wv_items}
            st.write(", ".join(sorted(i["name"] for i in osm_items if i["name"].lower() not in wv_names)))

    if not sorted_items:
        if filter_text:
            st.info(f"No attractions matched filter “{name_filter}”.")
        else:
            st.info("No attractions to show.")
        return

    header = f"### Top {len(sorted_items)} activities — sorted by *{sort_by.lower()}*"
    if filter_text:
        header += f" · filtered by “{name_filter}”"
    st.markdown(header)
    cols_per_row = 3
    for row_start in range(0, len(sorted_items), cols_per_row):
        row = sorted_items[row_start : row_start + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, item in zip(cols, row):
            with col:
                render_attraction_card(item)


if __name__ == "__main__":
    main()
