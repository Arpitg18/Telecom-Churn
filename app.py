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
    "museum": "$15",
    "gallery": "$12",
    "castle": "$15",
    "archaeological_site": "$10",
    "attraction": "$10",
    "ruins": "$8",
    "monument": "$5",
    "place_of_worship": "Free / donation",
    "memorial": "Free",
    "artwork": "Free",
    "viewpoint": "Free",
    "picnic_site": "Free",
    "park": "Free",
    "garden": "Free",
    "nature_reserve": "Free",
    "beach": "Free",
}
DEFAULT_PRICE = "$10"

CATEGORY_KEYS = ("tourism", "historic", "leisure", "amenity", "natural")


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
    tourism_re = "museum|attraction|gallery|theme_park|water_park|zoo|aquarium|viewpoint|artwork|picnic_site"
    historic_re = "monument|memorial|castle|ruins|archaeological_site"
    leisure_re = "park|garden|nature_reserve"
    amenity_re = "place_of_worship"
    natural_re = "beach"

    query = f"""
    [out:json][timeout:{OVERPASS_TIMEOUT}];
    (
      node["tourism"~"^({tourism_re})$"]["name"](around:{radius_m},{lat},{lon});
      way["tourism"~"^({tourism_re})$"]["name"](around:{radius_m},{lat},{lon});
      node["historic"~"^({historic_re})$"]["name"](around:{radius_m},{lat},{lon});
      way["historic"~"^({historic_re})$"]["name"](around:{radius_m},{lat},{lon});
      node["leisure"~"^({leisure_re})$"]["name"](around:{radius_m},{lat},{lon});
      way["leisure"~"^({leisure_re})$"]["name"](around:{radius_m},{lat},{lon});
      node["amenity"~"^({amenity_re})$"]["name"](around:{radius_m},{lat},{lon});
      way["amenity"~"^({amenity_re})$"]["name"](around:{radius_m},{lat},{lon});
      node["natural"~"^({natural_re})$"]["name"](around:{radius_m},{lat},{lon});
    );
    out center body {limit * 4};
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
        if last_status:
            st.error(f"Attractions API error: HTTP {last_status} (all mirrors busy — try again in a moment)")
        else:
            st.error("Attractions API unreachable — try again in a moment.")
        return []
    try:
        elements = resp.json().get("elements", [])
    except ValueError:
        return []

    seen_names = set()
    deduped = []
    for el in elements:
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        deduped.append(el)

    def rank_key(el):
        tags = el.get("tags") or {}
        has_wiki = bool(tags.get("wikipedia") or tags.get("wikidata"))
        has_image = bool(tags.get("image") or tags.get("wikimedia_commons"))
        return (0 if has_wiki else 1, 0 if has_image else 1, tags.get("name", ""))

    deduped.sort(key=rank_key)
    return deduped[:limit]


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


def get_price_estimate(tags: dict) -> str:
    for key in CATEGORY_KEYS:
        v = tags.get(key)
        if v and v in PRICE_TABLE:
            return PRICE_TABLE[v]
    return DEFAULT_PRICE


def category_label(tags: dict) -> str:
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


def render_attraction_card(element: dict) -> None:
    tags = element.get("tags") or {}
    name = tags.get("name", "Unnamed attraction")
    lat, lon = get_coords(element)
    label = category_label(tags)
    price = get_price_estimate(tags)

    summary = None
    if tags.get("wikipedia"):
        summary = fetch_wikipedia_summary(tags["wikipedia"])

    image = (summary or {}).get("thumbnail") or tags.get("image")
    description = (summary or {}).get("extract")

    with st.container(border=True):
        if image:
            st.image(image, use_container_width=True)
        st.subheader(name)
        st.caption(label)
        if description:
            st.write(_truncate(description))
        st.markdown(f"**Estimated price:** {price}")
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
        location = st.text_input("City / state / country", value="Paris")
        radius_km = st.number_input("Search radius (km)", min_value=1, max_value=50, value=10)
        limit = st.number_input("Max results", min_value=5, max_value=50, value=20)
        search = st.button("Search", type="primary", use_container_width=True)

    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Prices are static estimates by category — actual ticket prices vary. "
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

    with st.spinner("Fetching top attractions… (first search can take 10–20s)"):
        elements = fetch_attractions(geo["lat"], geo["lon"], int(radius_km) * 1000, int(limit))

    if not elements:
        st.info("No attractions found — try widening the radius or a different location.")
        return

    st.markdown(f"### Top {len(elements)} activities")
    cols_per_row = 3
    for row_start in range(0, len(elements), cols_per_row):
        row = elements[row_start : row_start + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, element in zip(cols, row):
            with col:
                render_attraction_card(element)


if __name__ == "__main__":
    main()
