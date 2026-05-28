# Top Tourist Attractions

A small Streamlit app that lets you pick a **city, state, or country** and shows the **top tourist activities** there along with an **estimated price** for each.

- Data: [OpenTripMap API](https://opentripmap.io) (free tier).
- Prices: static estimates keyed on the attraction category (museum, park, theme park, etc.) — real ticket prices vary; treat these as ballpark figures.

## Deploy on Streamlit Community Cloud (no install, works from mobile)

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. Tap **New app**, pick repo `arpitg18/telecom-churn`, branch `claude/tourist-attractions-app-4lanv`, main file path `app.py`.
3. Under **Advanced settings → Secrets**, paste:
   ```
   OPENTRIPMAP_API_KEY = "your-key-here"
   ```
   Get a free key at [opentripmap.io/product](https://opentripmap.io/product).
4. Tap **Deploy**. After ~1 minute you'll get a public URL you can open on your phone.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then paste your key
streamlit run app.py
```

Opens at <http://localhost:8501>.

## How it works

1. **Geocode** the location you typed (`/geoname` endpoint).
2. **Find top-rated attractions** within the chosen radius (`/radius?rate=` endpoint).
3. **Fetch details** for each (`/xid/<id>`) — image, description, categories.
4. **Estimate a price** by looking up the attraction's category in a static table:

   | Category                       | Estimated price    |
   | ------------------------------ | ------------------ |
   | Amusement parks                | $60                |
   | Theatres & entertainment       | $45                |
   | Sport                          | $25                |
   | Food                           | $20                |
   | Museums                        | $15                |
   | Historic sites                 | $10                |
   | Monuments & memorials          | $5                 |
   | Religious sites                | Free / donation    |
   | Natural / parks                | Free               |
   | Urban environment              | Free               |
   | Anything else                  | $10                |

Results are cached for an hour so repeated searches are instant.

## Notes

- The free OpenTripMap tier is rate-limited; if you see a "Rate limit hit" warning, wait a minute and retry.
- `.streamlit/secrets.toml` is in `.gitignore` — your key won't be committed.
