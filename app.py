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
      relation["tourism"~"^({tourism_re})$"]["name"]["wikipedia"](around:{radius_m},{lat},{lon});
      node["historic"~"^({historic_re})$"]["name"](around:{radius_m},{lat},{lon});
      way["historic"~"^({historic_re})$"]["name"](around:{radius_m},{lat},{lon});
      relation["historic"~"^({historic_re})$"]["name"]["wikipedia"](around:{radius_m},{lat},{lon});
      node["leisure"~"^({leisure_re})$"]["name"](around:{radius_m},{lat},{lon});
      way["leisure"~"^({leisure_re})$"]["name"](around:{radius_m},{lat},{lon});
      node["amenity"~"^({amenity_re})$"]["name"](around:{radius_m},{lat},{lon});
      way["amenity"~"^({amenity_re})$"]["name"](around:{radius_m},{lat},{lon});
      node["natural"~"^({natural_re})$"]["name"](around:{radius_m},{lat},{lon});
      way["natural"~"^({natural_re})$"]["name"]["wikipedia"](around:{radius_m},{lat},{lon});
      relation["natural"~"^({natural_re})$"]["name"]["wikipedia"](around:{radius_m},{lat},{lon});
      node["aerialway"~"^({aerialway_re})$"]["name"](around:{radius_m},{lat},{lon});
      node["place"~"^({place_re})$"]["name"]["wikipedia"](around:{radius_m},{lat},{lon});
      way["place"~"^({place_re})$"]["name"]["wikipedia"](around:{radius_m},{lat},{lon});
      relation["place"~"^({place_re})$"]["name"]["wikipedia"](around:{radius_m},{lat},{lon});
    );
    out center body {limit * 8};
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

    seen_names = set()
    deduped = []
    for el in elements:
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        deduped.append(el)
    return deduped


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


def enrich(element: dict) -> dict:
    tags = element.get("tags") or {}
    wiki_tag = tags.get("wikipedia")
    summary = fetch_wikipedia_summary(wiki_tag) if wiki_tag else None
    pageviews = fetch_pageviews(wiki_tag) if wiki_tag else 0
    return {
        "element": element,
        "tags": tags,
        "name": tags.get("name", "Unnamed attraction"),
        "summary": summary,
        "pageviews": pageviews,
        "price_str": get_price_estimate(tags),
    }


def sort_enriched(items: list, sort_by: str) -> list:
    if sort_by == "Most famous":
        return sorted(items, key=lambda i: (-i["pageviews"], i["name"].lower()))
    if sort_by == "Cheapest first":
        return sorted(items, key=lambda i: (price_numeric(i["price_str"]), i["name"].lower()))
    if sort_by == "Most expensive first":
        return sorted(items, key=lambda i: (-price_numeric(i["price_str"]), i["name"].lower()))
    return sorted(items, key=lambda i: i["name"].lower())


def render_attraction_card(item: dict) -> None:
    tags = item["tags"]
    name = item["name"]
    lat, lon = get_coords(item["element"])
    label = category_label(tags)
    price = item["price_str"]
    summary = item["summary"] or {}
    image = summary.get("thumbnail") or tags.get("image")
    description = summary.get("extract")
    pageviews = item["pageviews"]

    with st.container(border=True):
        if image:
            st.image(image, use_container_width=True)
        st.subheader(name)
        st.caption(label)
        if description:
            st.write(_truncate(description))
        st.markdown(f"**Estimated price:** {price}")
        if pageviews:
            st.caption(f"~{pageviews:,} Wikipedia views (last 30 days)")
        if lat is not None and lon is not None:
            st.markdown(
                f"[View on map](https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon})"
            )


def main() -> None:
    st.set_page_config(page_title="Top Tourist Attractions", page_icon="\U0001f5fa️", layout="wide")
    st.title("\U0001f5fa️ Top Tourist Attractions")
    st.caption("Pick a city, state, or country and see top activities with estimated prices.")

    with st.sidebar:
        st.markdown("### Search")
        location = st.text_input("City / state / country", value="Lucerne")
        radius_km = st.number_input("Search radius (km)", min_value=1, max_value=100, value=30)
        limit = st.number_input("Max results", min_value=5, max_value=50, value=20)
        sort_by = st.selectbox("Sort by", SORT_OPTIONS, index=0)
        search = st.button("Search", type="primary", use_container_width=True)

    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Prices are static estimates by category — actual ticket prices vary. "
        "“Most famous” ranks by Wikipedia pageviews (last 30 days). "
        "Data: [OpenStreetMap](https://openstreetmap.org) + [Wikipedia](https://wikipedia.org). "
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

    try:
        with st.spinner("Fetching attractions from OpenStreetMap…"):
            elements = fetch_attractions(geo["lat"], geo["lon"], int(radius_km) * 1000, int(limit))
    except RuntimeError as e:
        st.error(str(e))
        return

    if not elements:
        st.info("No attractions found — try widening the radius or a different location.")
        return

    with st.spinner(f"Ranking {len(elements)} attractions by Wikipedia popularity… (cached after first run)"):
        enriched = [enrich(el) for el in elements]

    enriched = sort_enriched(enriched, sort_by)[: int(limit)]

    st.markdown(f"### Top {len(enriched)} activities — sorted by *{sort_by.lower()}*")
    cols_per_row = 3
    for row_start in range(0, len(enriched), cols_per_row):
        row = enriched[row_start : row_start + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, item in zip(cols, row):
            with col:
                render_attraction_card(item)


if __name__ == "__main__":
    main()
