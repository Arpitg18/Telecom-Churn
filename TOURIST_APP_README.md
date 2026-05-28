# Top Tourist Attractions

A small Streamlit app that lets you pick a **city, state, or country** and shows the **top tourist activities** there along with an **estimated price** for each.

- **No API key required.**
- Attractions data: [OpenStreetMap](https://openstreetmap.org) via the [Overpass API](https://overpass-api.de) and [Nominatim](https://nominatim.openstreetmap.org).
- Descriptions & images: [Wikipedia REST API](https://en.wikipedia.org/api/rest_v1/).
- Prices: static estimates keyed on the attraction category (museum, park, theme park, etc.) — real ticket prices vary; treat these as ballpark figures.

## Deploy on Streamlit Community Cloud (no install, works from mobile)

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. Tap **Create app → Deploy a public app from GitHub**.
3. Fill in:
   - **Repository:** `arpitg18/telecom-churn`
   - **Branch:** `claude/tourist-attractions-app-4lanv`
   - **Main file path:** `app.py`
4. Tap **Deploy**. No secrets needed. After ~1 minute you'll get a public URL you can open on your phone.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Opens at <http://localhost:8501>.

## How it works

1. **Geocode** the location you typed via Nominatim → lat/lon.
2. **Find attractions** within the chosen radius via Overpass API — queries OSM nodes/ways tagged `tourism=*`, `historic=*`, `leisure=park|garden|nature_reserve`, `amenity=place_of_worship`, `natural=beach`.
3. **Rank** results that have a `wikipedia` or `image` tag higher, so attractions with rich data show first.
4. **Fetch details** (extract + thumbnail) from Wikipedia for places with a `wikipedia` tag.
5. **Estimate a price** from the OSM category:

   | Category                       | Estimated price    |
   | ------------------------------ | ------------------ |
   | Theme park                     | $60                |
   | Water park                     | $45                |
   | Aquarium                       | $30                |
   | Zoo                            | $25                |
   | Museum                         | $15                |
   | Castle                         | $15                |
   | Gallery                        | $12                |
   | Attraction / archaeological    | $10                |
   | Ruins                          | $8                 |
   | Monument                       | $5                 |
   | Place of worship               | Free / donation    |
   | Memorial / viewpoint / artwork | Free               |
   | Park / garden / beach / nature | Free               |
   | Anything else                  | $10                |

Results are cached for an hour so repeated searches are instant.

## Notes

- First search for a new location takes 10–20 seconds (Overpass API can be slow under load); subsequent ones are instant thanks to caching.
- Nominatim and Overpass have public rate limits — fine for personal demo use.
