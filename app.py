import requests
import streamlit as st

BASE_URL = "https://api.opentripmap.com/0.1/en/places"
REQUEST_TIMEOUT = 15

PRICE_TABLE = [
    ("amusement_parks", "$60"),
    ("theatres_and_entertainments", "$45"),
    ("sport", "$25"),
    ("foods", "$20"),
    ("museums", "$15"),
    ("historic", "$10"),
    ("monuments_and_memorials", "$5"),
    ("religion", "Free / donation"),
    ("natural", "Free"),
    ("urban_environment", "Free"),
]
DEFAULT_PRICE = "$10"


def get_api_key() -> str:
    secret_key = ""
    try:
        secret_key = st.secrets.get("OPENTRIPMAP_API_KEY", "")
    except Exception:
        secret_key = ""

    if secret_key:
        return secret_key

    st.sidebar.markdown("### OpenTripMap API key")
    st.sidebar.caption("Get a free key at [opentripmap.io](https://opentripmap.io/product).")
    return st.sidebar.text_input("API key", type="password", key="api_key_input").strip()


def get_price_estimate(kinds: str) -> str:
    if not kinds:
        return DEFAULT_PRICE
    tokens = {k.strip() for k in kinds.split(",")}
    for token, price in PRICE_TABLE:
        if token in tokens:
            return price
    return DEFAULT_PRICE


def _handle_response(resp: requests.Response):
    if resp.status_code == 429:
        st.warning("Rate limit hit — wait a minute and retry.")
        return None
    if resp.status_code == 401 or resp.status_code == 403:
        st.error("API key was rejected. Double-check your OpenTripMap key.")
        return None
    if not resp.ok:
        st.error(f"API error: HTTP {resp.status_code}")
        return None
    try:
        return resp.json()
    except ValueError:
        st.error("API returned an unexpected response.")
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def geocode_location(name: str, api_key: str):
    try:
        resp = requests.get(
            f"{BASE_URL}/geoname",
            params={"name": name, "apikey": api_key},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        st.error(f"Network error while geocoding: {e}")
        return None

    data = _handle_response(resp)
    if not isinstance(data, dict) or data.get("status") == "NOT_FOUND" or "lat" not in data:
        return None
    return data


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_attractions(lat, lon, radius_m, min_rate, limit, api_key):
    try:
        resp = requests.get(
            f"{BASE_URL}/radius",
            params={
                "radius": radius_m,
                "lon": lon,
                "lat": lat,
                "rate": min_rate,
                "format": "json",
                "limit": limit,
                "apikey": api_key,
            },
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        st.error(f"Network error while fetching attractions: {e}")
        return []

    data = _handle_response(resp)
    if not isinstance(data, list):
        return []
    return data


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_place_details(xid: str, api_key: str) -> dict:
    try:
        resp = requests.get(
            f"{BASE_URL}/xid/{xid}",
            params={"apikey": api_key},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return {}
    if not resp.ok:
        return {}
    try:
        return resp.json() or {}
    except ValueError:
        return {}


def _truncate(text: str, max_len: int = 280) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rsplit(" ", 1)[0] + "…"


def _format_kinds(kinds: str, max_tags: int = 4) -> str:
    if not kinds:
        return ""
    tokens = [k.strip().replace("_", " ") for k in kinds.split(",") if k.strip()]
    return " · ".join(tokens[:max_tags])


def render_attraction_card(place: dict) -> None:
    name = place.get("name") or "Unnamed attraction"
    kinds = place.get("kinds", "")
    preview = place.get("preview") or {}
    image_url = preview.get("source") if isinstance(preview, dict) else None
    description = ""
    if isinstance(place.get("wikipedia_extracts"), dict):
        description = place["wikipedia_extracts"].get("text", "")
    if not description:
        description = place.get("info", {}).get("descr", "") if isinstance(place.get("info"), dict) else ""

    point = place.get("point") or {}
    lat = point.get("lat")
    lon = point.get("lon")

    price = get_price_estimate(kinds)

    with st.container(border=True):
        if image_url:
            st.image(image_url, use_container_width=True)
        st.subheader(name)
        if kinds:
            st.caption(_format_kinds(kinds))
        if description:
            st.write(_truncate(description))
        st.markdown(f"**Estimated price:** {price}")
        if lat is not None and lon is not None:
            st.markdown(
                f"[View on map](https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon})"
            )


def main() -> None:
    st.set_page_config(page_title="Top Tourist Attractions", page_icon="🗺️", layout="wide")
    st.title("🗺️ Top Tourist Attractions")
    st.caption("Pick a city, state, or country and see top-rated activities with estimated prices.")

    api_key = get_api_key()

    with st.sidebar:
        st.markdown("### Search")
        location = st.text_input("City / state / country", value="Paris")
        radius_km = st.number_input("Search radius (km)", min_value=1, max_value=50, value=10)
        min_rate = st.slider("Minimum rating", min_value=1, max_value=3, value=2)
        limit = st.number_input("Max results", min_value=5, max_value=50, value=20)
        search = st.button("Search", type="primary", use_container_width=True)

    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Prices are static estimates by category — actual ticket prices vary. "
        "Data: [OpenTripMap](https://opentripmap.io)."
    )

    if not search:
        st.info("Enter a location in the sidebar and click **Search** to begin.")
        return

    if not api_key:
        st.warning("An OpenTripMap API key is required. Add it in the sidebar or in `.streamlit/secrets.toml`.")
        return

    if not location.strip():
        st.warning("Please enter a location.")
        return

    with st.spinner(f"Looking up '{location}'…"):
        geo = geocode_location(location.strip(), api_key)

    if not geo:
        st.error("Location not found — try a different spelling or a more specific name.")
        return

    place_name = geo.get("name", location)
    country = geo.get("country", "")
    lat, lon = geo["lat"], geo["lon"]
    header = f"📍 {place_name}" + (f", {country}" if country else "")
    st.subheader(header)
    st.caption(f"Coordinates: {lat:.4f}, {lon:.4f}")

    with st.spinner("Fetching top attractions…"):
        raw_places = fetch_attractions(lat, lon, int(radius_km) * 1000, int(min_rate), int(limit), api_key)

    if not raw_places:
        st.info("No attractions found — try widening the radius or lowering the rating threshold.")
        return

    raw_places.sort(key=lambda p: p.get("rate", 0), reverse=True)

    details = []
    progress = st.progress(0.0, text="Loading attraction details…")
    for i, place in enumerate(raw_places, start=1):
        xid = place.get("xid")
        if not xid:
            continue
        detail = fetch_place_details(xid, api_key)
        if not detail or not detail.get("name"):
            continue
        details.append(detail)
        progress.progress(i / len(raw_places), text=f"Loading attraction details… ({i}/{len(raw_places)})")
    progress.empty()

    if not details:
        st.info("Found locations but couldn't load details. Try again or widen the radius.")
        return

    st.markdown(f"### Top {len(details)} activities")
    cols_per_row = 3
    for row_start in range(0, len(details), cols_per_row):
        row = details[row_start : row_start + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, place in zip(cols, row):
            with col:
                render_attraction_card(place)


if __name__ == "__main__":
    main()
