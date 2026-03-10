"""
FlightAgent v4 — Worldwide Flight Explorer
==========================================
Install:  pip install requests

Usage:
    agent = FlightAgent()                            # auto-finds airports.json
    agent = FlightAgent("airports.json")             # local path
    agent = FlightAgent("data/airports.json")        # nested path

Data sources (ALL free, zero signup):
    ✅ airports.json   — Your worldwide airports file (8000+ airports)
    ✅ ADSB.lol        — Live aircraft positions (real ADS-B transponder data)
    ✅ Wikipedia API   — Airport / city descriptions

JSON schema expected (matches your format exactly):
    {
      "code": "AAQ",           ← IATA code  (primary key)
      "lat":  "44.9",
      "lon":  "37.3167",
      "name": "Olkhovka Airport",
      "city": "Novorossiysk",
      "state": "Krasnodarskiy Kray",
      "country": "Russia",
      "tz":   "Europe/Moscow",
      "icao": "URKA",
      "direct_flights": "24",
      "carriers": "15",
      "phone": "", "url": "", "email": "",
      "runway_length": null, "elev": null,
      "woeid": "12516605", "type": "Airports"
    }
"""

import requests, math, json, os, sys
from typing import List, Dict, Any, Optional

HEADERS = {"User-Agent": "SmartTripAI-FlightAgent/4.0"}

# ── Common search paths for airports.json ─────────────────────────────────────
AIRPORTS_SEARCH_PATHS = [
    "airports.json",                   # current directory
    "data/airports.json",
    "../airports.json",
]

# ── Airline callsign prefix → name ────────────────────────────────────────────
AIRLINE_PREFIXES = {
    "IGO":"IndiGo",            "AIC":"Air India",          "SEJ":"SpiceJet",
    "SXB":"SpiceJet",          "GOW":"GoAir",              "IAD":"Air India Express",
    "VGI":"Vistara",           "ABY":"AirAsia India",      "IAX":"Air India Express",
    "UAE":"Emirates",          "ETD":"Etihad Airways",     "QTR":"Qatar Airways",
    "SIA":"Singapore Airlines","MAS":"Malaysia Airlines",  "THA":"Thai Airways",
    "QFA":"Qantas",            "BAW":"British Airways",    "DLH":"Lufthansa",
    "AFR":"Air France",        "KLM":"KLM",                "AAL":"American Airlines",
    "DAL":"Delta Air Lines",   "UAL":"United Airlines",    "CCA":"Air China",
    "CES":"China Eastern",     "CSN":"China Southern",     "ANA":"ANA All Nippon",
    "JAL":"Japan Airlines",    "KAL":"Korean Air",         "AAR":"Asiana Airlines",
    "SVA":"Saudi Arabian Airlines","ETH":"Ethiopian Airlines","KQA":"Kenya Airways",
    "MSR":"EgyptAir",          "RAM":"Royal Air Maroc",    "PIA":"Pakistan Intl Airlines",
    "THY":"Turkish Airlines",  "IBE":"Iberia",             "TAP":"TAP Air Portugal",
    "SAS":"Scandinavian Airlines","FIN":"Finnair",          "AUA":"Austrian Airlines",
    "SWR":"SWISS",             "BEL":"Brussels Airlines",  "WZZ":"Wizz Air",
    "RYR":"Ryanair",           "EZY":"easyJet",            "VLG":"Vueling",
    "FDB":"flydubai",          "GFA":"Gulf Air",           "OMA":"Oman Air",
    "RJA":"Royal Jordanian",   "MEA":"Middle East Airlines","AFL":"Aeroflot",
    "PAL":"Philippine Airlines","CPA":"Cathay Pacific",    "HVN":"Vietnam Airlines",
    "GAR":"Garuda Indonesia",  "LNI":"Lion Air",           "AXM":"AirAsia",
    "MXD":"Malindo Air",       "BTK":"Batik Air",          "AWQ":"Citilink",
    "UAP":"Ural Airlines",     "SDM":"Rossiya Airlines",
}

# ══════════════════════════════════════════════════════════════════════════════
#  AIRPORT DATABASE — loads your airports.json
# ══════════════════════════════════════════════════════════════════════════════

class AirportDB:
    """
    Loads and indexes your airports.json with O(1) IATA/ICAO lookup.
    Handles both array format  [ {...}, {...} ]
    and dict format            { "MAA": {...}, "BOM": {...} }
    """

    def __init__(self, path: Optional[str] = None):
        self._iata:    Dict[str, Dict] = {}
        self._icao:    Dict[str, Dict] = {}
        self._all:     List[Dict]       = []
        self._path     = "not loaded"

        loaded = False

        # Try explicit path first
        if path and os.path.exists(path):
            loaded = self._load(path)

        # Auto-search common paths
        if not loaded:
            for p in AIRPORTS_SEARCH_PATHS:
                if os.path.exists(p):
                    loaded = self._load(p)
                    if loaded: break

        if not loaded:
            print("⚠️  airports.json not found.")
            print("   Place airports.json in the same folder as this script, or specify a path.")
            print("   Loaded 0 airports — search will return no results until file is provided.")

    def _load(self, path: str) -> bool:
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)

            # Normalise to list
            if isinstance(raw, list):
                records = raw
            elif isinstance(raw, dict):
                records = list(raw.values())
            else:
                print(f"⚠️  Unrecognised JSON structure in {path}")
                return False

            ok = 0
            for ap in records:
                if not isinstance(ap, dict):
                    continue
                code = str(ap.get("code") or ap.get("iata") or "").strip().upper()
                try:
                    lat = float(ap.get("lat") or ap.get("latitude") or 0)
                    lon = float(ap.get("lon") or ap.get("longitude") or 0)
                except (ValueError, TypeError):
                    continue
                if not code or lat == 0 and lon == 0:
                    continue

                ap["_iata"] = code
                ap["_lat"]  = lat
                ap["_lon"]  = lon
                # Normalise common alternate key names
                ap.setdefault("code",           code)
                ap.setdefault("name",           ap.get("airport_name", ap.get("Name", "Unknown")))
                ap.setdefault("city",           ap.get("City", ap.get("municipality", "")))
                ap.setdefault("country",        ap.get("Country", ap.get("iso_country", "")))
                ap.setdefault("state",          ap.get("State", ap.get("iso_region", "")))
                ap.setdefault("tz",             ap.get("timezone", ap.get("tz_database", "")))
                ap.setdefault("icao",           ap.get("icao", ap.get("ident", "")))
                ap.setdefault("direct_flights", ap.get("direct_flights", "N/A"))
                ap.setdefault("carriers",       ap.get("carriers", "N/A"))
                ap.setdefault("phone",          ap.get("phone", ""))
                ap.setdefault("url",            ap.get("url", ap.get("website", "")))
                ap.setdefault("type",           ap.get("type", "Airports"))
                ap.setdefault("runway_length",  ap.get("runway_length"))
                ap.setdefault("elev",           ap.get("elev", ap.get("elevation_ft")))

                self._all.append(ap)
                self._iata[code] = ap
                icao = str(ap.get("icao") or "").strip().upper()
                if icao:
                    self._icao[icao] = ap
                ok += 1

            self._path = path
            print(f"✅ Loaded {ok:,} airports from  {path}")
            return True

        except Exception as e:
            print(f"⚠️  Failed to load {path}: {e}")
            return False

    # ── Lookup ────────────────────────────────────────────────────────────────

    def by_iata(self, code: str) -> Optional[Dict]:
        return self._iata.get(code.strip().upper())

    def by_icao(self, code: str) -> Optional[Dict]:
        return self._icao.get(code.strip().upper())

    def find(self, query: str, limit: int = 20) -> List[Dict]:
        """
        Smart search: IATA → ICAO → exact city/country → partial match.
        Returns results sorted by relevance.
        """
        q = query.strip().lower()
        if not q:
            return []

        # Exact IATA / ICAO
        exact = self.by_iata(query) or self.by_icao(query)
        if exact:
            return [exact]

        tier1, tier2, tier3 = [], [], []
        for ap in self._all:
            city    = ap.get("city", "").lower()
            country = ap.get("country", "").lower()
            name    = ap.get("name", "").lower()
            iata    = ap.get("_iata", "").lower()
            state   = ap.get("state", "").lower()

            if q == city or q == country:
                tier1.append(ap)
            elif q in city or q in country:
                tier2.append(ap)
            elif q in name or q in state:
                tier3.append(ap)

        results = tier1 + tier2 + tier3
        return results[:limit]

    def by_country(self, country: str, limit: int = 200) -> List[Dict]:
        q = country.strip().lower()
        return [ap for ap in self._all if q in ap.get("country", "").lower()][:limit]

    def by_city(self, city: str) -> List[Dict]:
        q = city.strip().lower()
        return [ap for ap in self._all if q in ap.get("city", "").lower()]

    def nearest(self, lat: float, lon: float, n: int = 5) -> List[Dict]:
        scored = sorted(self._all, key=lambda ap: _hav(lat, lon, ap["_lat"], ap["_lon"]))
        results = scored[:n]
        for ap in results:
            ap["_dist_km"] = round(_hav(lat, lon, ap["_lat"], ap["_lon"]), 1)
        return results

    def resolve(self, query: str) -> Optional[Dict]:
        """Best single match for a city name, IATA, or ICAO."""
        results = self.find(query, limit=1)
        return results[0] if results else None

    @property
    def total(self) -> int:
        return len(self._all)

    @property
    def countries(self) -> List[str]:
        return sorted(set(ap.get("country", "") for ap in self._all if ap.get("country")))

    @property
    def stats(self) -> Dict:
        return {
            "total_airports": self.total,
            "countries":      len(self.countries),
            "with_icao":      len(self._icao),
            "source_file":    self._path,
        }


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def _hav(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a    = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def _est_flight_time(dist_km: float) -> str:
    hrs = dist_km / 850 + 0.5
    h, m = int(hrs), int((hrs % 1) * 60)
    return f"~{h}h {m:02d}m"

def _get_airline(callsign: str) -> str:
    if not callsign: return "Unknown"
    return AIRLINE_PREFIXES.get(callsign[:3].upper(), f"({callsign[:3]})")

def _fetch_adsb(lat: float, lon: float, radius_nm: int = 60) -> List[Dict]:
    """Live aircraft via ADSB.lol — zero signup, real transponder data."""
    try:
        r = requests.get(
            f"https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{radius_nm}",
            headers=HEADERS, timeout=15
        )
        return r.json().get("ac", []) if r.status_code == 200 else []
    except Exception as e:
        print(f"[ADSB] {e}"); return []

def _parse_ac(ac: Dict, ref_lat: float, ref_lon: float) -> Optional[Dict]:
    cs = (ac.get("flight") or "").strip()
    if not cs: return None
    lat, lon = ac.get("lat"), ac.get("lon")
    return {
        "callsign":      cs,
        "airline":       _get_airline(cs),
        "icao_hex":      ac.get("hex", "N/A"),
        "aircraft_type": ac.get("t") or ac.get("type", "N/A"),
        "altitude_ft":   ac.get("alt_baro") or ac.get("alt_geom", "N/A"),
        "speed_kmh":     round((ac.get("gs") or 0) * 1.852) or "N/A",
        "heading_deg":   ac.get("track", "N/A"),
        "lat": lat, "lon": lon,
        "on_ground":     bool(ac.get("on_ground")),
        "squawk":        ac.get("squawk", "N/A"),
        "registration":  ac.get("r", "N/A"),
        "dist_km":       round(_hav(ref_lat, ref_lon, lat or ref_lat, lon or ref_lon), 1) if lat else "N/A",
        "fr24_url":      f"https://www.flightradar24.com/{cs}",
        "adsb_url":      f"https://globe.adsbexchange.com/?icao={ac.get('hex','')}",
        "maps_url":      f"https://www.google.com/maps?q={lat},{lon}" if lat else None,
    }

def _booking_links(orig: str, dest: str, date: str) -> Dict[str, str]:
    """Pre-filled search URLs — no API key needed, works globally."""
    dt = date.replace("-", "")
    return {
        "google_flights": f"https://www.google.com/travel/flights?q=flights+from+{orig}+to+{dest}+on+{date}",
        "skyscanner":     f"https://www.skyscanner.net/transport/flights/{orig}/{dest}/{dt}/",
        "kayak":          f"https://www.kayak.com/flights/{orig}-{dest}/{date}/1adults",
        "makemytrip":     f"https://www.makemytrip.com/flight/search?tripType=O&itinerary={orig}-{dest}-{date}&paxType=A-1_C-0_I-0&cabinClass=E",
        "ixigo":          f"https://www.ixigo.com/flights/{orig}/{dest}/{date}/1/0/0/E/0/none",
        "cleartrip":      f"https://www.cleartrip.com/flights/results?adults=1&class=Economy&depart_date={date}&from={orig}&to={dest}",
        "easemytrip":     f"https://www.easemytrip.com/flights/flight-search.html?org={orig}&dest={dest}&ddate={date}&adult=1&cls=E",
    }


# ══════════════════════════════════════════════════════════════════════════════
#  FLIGHT AGENT v4
# ══════════════════════════════════════════════════════════════════════════════

class FlightAgent:
    """
    FlightAgent v4 — Worldwide airport database + Live ADS-B flights.

    API:
        search_flights(origin, dest, date)   → live aircraft + route info + booking links
        live_near_airport(airport, radius)   → all live flights around any airport
        find_airport(query)                  → search by city / country / IATA / ICAO
        airports_by_country(country)         → all airports in a country
        airports_by_city(city)               → airports in a city
        route_info(origin, dest)             → distance, flight time, timezone
        nearest_airports(lat, lon, n)        → closest airports to a coordinate
        get_booking_links(orig, dest, date)  → pre-filled links (no API key)
        db.stats                             → total airports, countries, source file
    """

    def __init__(self, airports_json_path: Optional[str] = None):
        self.db = AirportDB(airports_json_path)
        if self.db.total > 0:
            s = self.db.stats
            print(f"[FlightAgent] ✅ {s['total_airports']:,} airports · "
                  f"{s['countries']} countries · {s['with_icao']:,} ICAO codes")

    # ── Airport search ────────────────────────────────────────────────────────

    def find_airport(self, query: str) -> List[Dict]:
        """
        Search airports by any field.
        Examples:
            find_airport("MAA")            → Chennai airport
            find_airport("Novorossiysk")   → AAQ airport
            find_airport("Russia")         → all Russian airports
            find_airport("URKA")           → by ICAO
        """
        return self._enrich(self.db.find(query))

    def airports_by_country(self, country: str) -> List[Dict]:
        return self._enrich(self.db.by_country(country))

    def airports_by_city(self, city: str) -> List[Dict]:
        return self._enrich(self.db.by_city(city))

    def nearest_airports(self, lat: float, lon: float, n: int = 5) -> List[Dict]:
        return self._enrich(self.db.nearest(lat, lon, n))

    def _enrich(self, airports: List[Dict]) -> List[Dict]:
        out = []
        for ap in airports:
            ap = dict(ap)
            lat, lon = ap.get("_lat", 0), ap.get("_lon", 0)
            ap["maps_url"] = f"https://www.google.com/maps?q={lat},{lon}"
            ap["fr24_url"] = f"https://www.flightradar24.com/airport/{ap.get('code','').lower()}"
            ap["wiki_url"] = f"https://en.wikipedia.org/wiki/{ap.get('city','').replace(' ','_')}_airport"
            out.append(ap)
        return out

    # ── Route info ────────────────────────────────────────────────────────────

    def route_info(self, origin: str, destination: str) -> Dict[str, Any]:
        """Distance, estimated flight time, timezone between two airports."""
        orig = self.db.resolve(origin)
        dest = self.db.resolve(destination)
        if not orig: return {"error": f"Airport not found: '{origin}'"}
        if not dest: return {"error": f"Airport not found: '{destination}'"}

        dist = round(_hav(orig["_lat"], orig["_lon"], dest["_lat"], dest["_lon"]), 1)
        return {
            "origin":               f"{orig['code']} — {orig['name']}, {orig['city']}, {orig['country']}",
            "destination":          f"{dest['code']} — {dest['name']}, {dest['city']}, {dest['country']}",
            "origin_iata":          orig["code"],
            "dest_iata":            dest["code"],
            "distance_km":          dist,
            "distance_miles":       round(dist * 0.621371, 1),
            "est_flight_time":      _est_flight_time(dist),
            "origin_tz":            orig.get("tz", "N/A"),
            "destination_tz":       dest.get("tz", "N/A"),
            "origin_direct_routes": orig.get("direct_flights", "N/A"),
            "dest_direct_routes":   dest.get("direct_flights", "N/A"),
            "origin_carriers":      orig.get("carriers", "N/A"),
            "dest_carriers":        dest.get("carriers", "N/A"),
            "origin_runway_m":      orig.get("runway_length", "N/A"),
            "dest_runway_m":        dest.get("runway_length", "N/A"),
            "origin_elev_ft":       orig.get("elev", "N/A"),
            "dest_elev_ft":         dest.get("elev", "N/A"),
        }

    # ── Live flight search ────────────────────────────────────────────────────

    def search_flights(self, origin: str, destination: str, date: str) -> Dict[str, Any]:
        """
        Returns:
          - route info (distance, time, timezones)
          - live aircraft near both airports (ADS-B)
          - on-route flights (callsigns near both)
          - pre-filled booking links (Google Flights, Skyscanner, MakeMyTrip…)

        date format: YYYY-MM-DD
        """
        orig = self.db.resolve(origin)
        dest = self.db.resolve(destination)
        if not orig: return {"error": f"Airport not found: '{origin}'"}
        if not dest: return {"error": f"Airport not found: '{destination}'"}

        print(f"\n✈  {orig['code']} {orig['city']}, {orig['country']}"
              f"  →  {dest['code']} {dest['city']}, {dest['country']}")

        route = self.route_info(origin, destination)

        print(f"   Fetching live ADS-B near {orig['code']}…")
        orig_raw = _fetch_adsb(orig["_lat"], orig["_lon"])
        orig_ac  = [f for r in orig_raw if (f := _parse_ac(r, orig["_lat"], orig["_lon"]))]

        print(f"   Fetching live ADS-B near {dest['code']}…")
        dest_raw = _fetch_adsb(dest["_lat"], dest["_lon"])
        dest_ac  = [f for r in dest_raw if (f := _parse_ac(r, dest["_lat"], dest["_lon"]))]

        dest_calls  = {f["callsign"] for f in dest_ac}
        on_route    = [f for f in orig_ac if f["callsign"] in dest_calls]

        return {
            "origin":            orig,
            "destination":       dest,
            "date":              date,
            "route":             route,
            "live_near_origin":  orig_ac,
            "live_near_dest":    dest_ac,
            "on_route_flights":  on_route,
            "booking_links":     _booking_links(orig["code"], dest["code"], date),
            "note": (
                "Live positions from ADS-B transponders (real-time). "
                "Ticket prices not available free — use booking_links to search actual fares."
            ),
        }

    def live_near_airport(self, airport: str, radius_nm: int = 60) -> Dict[str, Any]:
        """All live aircraft within radius_nm nautical miles of an airport."""
        ap = self.db.resolve(airport)
        if not ap: return {"error": f"Airport not found: '{airport}'"}

        raw   = _fetch_adsb(ap["_lat"], ap["_lon"], radius_nm)
        all_f = [f for r in raw if (f := _parse_ac(r, ap["_lat"], ap["_lon"]))]

        return {
            "airport":   ap,
            "radius_nm": radius_nm,
            "total":     len(all_f),
            "airborne":  [f for f in all_f if not f["on_ground"]],
            "on_ground": [f for f in all_f if f["on_ground"]],
        }

    def get_booking_links(self, origin: str, destination: str, date: str) -> Dict[str, str]:
        orig = self.db.resolve(origin)
        dest = self.db.resolve(destination)
        if not orig: return {"error": f"Airport not found: '{origin}'"}
        if not dest: return {"error": f"Airport not found: '{destination}'"}
        return _booking_links(orig["code"], dest["code"], date)

    # ── Pretty print helpers ──────────────────────────────────────────────────

    def print_airport(self, ap: Dict):
        print(f"\n  ┌{'─'*55}")
        print(f"  │  ✈  {ap.get('name')}  [{ap.get('code')}]")
        print(f"  ├{'─'*55}")
        print(f"  │  City     : {ap.get('city')}, {ap.get('state','')}, {ap.get('country')}")
        print(f"  │  IATA/ICAO: {ap.get('code')} / {ap.get('icao','N/A')}")
        print(f"  │  Timezone : {ap.get('tz','N/A')}")
        print(f"  │  Lat/Lon  : {ap.get('_lat')}, {ap.get('_lon')}")
        print(f"  │  Elevation: {ap.get('elev','N/A')} ft")
        print(f"  │  Runway   : {ap.get('runway_length','N/A')}")
        print(f"  │  Routes   : {ap.get('direct_flights','N/A')} direct  ·  {ap.get('carriers','N/A')} carriers")
        print(f"  │  Phone    : {ap.get('phone') or 'N/A'}")
        print(f"  │  Website  : {ap.get('url') or 'N/A'}")
        print(f"  │  🗺  {ap.get('maps_url','')}")
        print(f"  │  ✈  {ap.get('fr24_url','')}")
        print(f"  └{'─'*55}")

    def print_route(self, route: Dict):
        if "error" in route:
            print(f"  ❌ {route['error']}"); return
        print(f"\n  ┌{'─'*58}")
        print(f"  │  ✈  {route['origin']}")
        print(f"  │     → {route['destination']}")
        print(f"  ├{'─'*58}")
        print(f"  │  Distance   : {route['distance_km']:,} km  ({route['distance_miles']:,} miles)")
        print(f"  │  Flight Time: {route['est_flight_time']}")
        print(f"  │  Origin TZ  : {route['origin_tz']}")
        print(f"  │  Dest TZ    : {route['destination_tz']}")
        print(f"  │  Routes     : {route['origin_direct_routes']} ↔ {route['dest_direct_routes']}")
        print(f"  └{'─'*58}")

    def print_flights(self, flights: List[Dict], title: str = "Live Flights"):
        if not flights:
            print(f"  {title}: no aircraft found")
            return
        print(f"\n  {title}  ({len(flights)} aircraft)")
        print(f"  {'─'*82}")
        print(f"  {'Callsign':<12}{'Airline':<22}{'Type':<8}{'Alt ft':<10}{'Speed':<10}{'Dist km':<9}Status")
        print(f"  {'─'*82}")
        for f in flights[:25]:
            status = "🛬 Ground" if f["on_ground"] else "✈ Airborne"
            print(f"  {f['callsign']:<12}{f['airline']:<22}{str(f['aircraft_type']):<8}"
                  f"{str(f['altitude_ft']):<10}{str(f['speed_kmh'])+'km/h':<10}"
                  f"{str(f['dist_km']):<9}{status}")

    def print_airports_table(self, airports: List[Dict], title: str = ""):
        if title:
            print(f"\n  {title}  ({len(airports)} results)")
        print(f"\n  {'IATA':<6}{'ICAO':<6}{'Name':<34}{'City':<18}{'Country':<20}{'Routes':<8}Carriers")
        print(f"  {'─'*100}")
        for ap in airports[:40]:
            print(f"  {ap.get('code',''):<6}{ap.get('icao',''):<6}{ap.get('name','')[:33]:<34}"
                  f"{ap.get('city','')[:17]:<18}{ap.get('country','')[:19]:<20}"
                  f"{ap.get('direct_flights','N/A'):<8}{ap.get('carriers','N/A')}")
        if len(airports) > 40:
            print(f"  … and {len(airports)-40} more airports")


# ══════════════════════════════════════════════════════════════════════════════
#  INTERACTIVE CLI  (python flight_agent_v4.py  OR  python flight_agent_v4.py airports.json)
# ══════════════════════════════════════════════════════════════════════════════

def run_cli():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    agent = FlightAgent(path)

    if agent.db.total == 0:
        print("\n❌ No airports loaded. Provide airports.json to continue.\n")
        return

    s = agent.db.stats
    print(f"\n{'='*62}")
    print(f"  ✈️   FlightAgent v4 — Worldwide Airport & Flight Explorer")
    print(f"       {s['total_airports']:,} airports  ·  {s['countries']} countries")
    print(f"{'='*62}")

    MENU = """
  [1]  Search flights (live ADS-B + booking links)
  [2]  Live aircraft near airport
  [3]  Find airport  (city / country / IATA / ICAO / name)
  [4]  All airports in a country
  [5]  All airports in a city
  [6]  Route info  (distance · flight time · timezones)
  [7]  Nearest airports to lat/lon
  [8]  Booking links only
  [9]  Database stats
  [q]  Quit
"""
    while True:
        print(MENU)
        c = input("  👉 Choose: ").strip().lower()

        if c == "1":
            o = input("  ✈  From (city / IATA): ").strip()
            d = input("  ✈  To   (city / IATA): ").strip()
            dt= input("  📅 Date (YYYY-MM-DD) : ").strip()
            r = agent.search_flights(o, d, dt)
            if "error" in r: print(f"  ❌ {r['error']}"); continue
            agent.print_route(r["route"])
            agent.print_flights(r["live_near_origin"],  f"Live near {r['origin']['code']}")
            agent.print_flights(r["on_route_flights"],  "On-route (near both airports)")
            print("\n  📲 Book tickets:")
            for site, url in r["booking_links"].items():
                print(f"     {site:<20}: {url}")

        elif c == "2":
            ap = input("  ✈  Airport (IATA / city): ").strip()
            nm = input("  📡 Radius NM [60]: ").strip()
            r  = agent.live_near_airport(ap, int(nm) if nm.isdigit() else 60)
            if "error" in r: print(f"  ❌ {r['error']}"); continue
            agent.print_airport(r["airport"])
            agent.print_flights(r["airborne"],  f"Airborne near {r['airport']['code']}")
            agent.print_flights(r["on_ground"], f"On ground at {r['airport']['code']}")

        elif c == "3":
            q = input("  🔎 Search: ").strip()
            results = agent.find_airport(q)
            if not results: print("  ❌ Nothing found."); continue
            agent.print_airports_table(results, f"Results for '{q}'")
            if len(results) == 1:
                agent.print_airport(results[0])

        elif c == "4":
            country = input("  🌍 Country: ").strip()
            results  = agent.airports_by_country(country)
            agent.print_airports_table(results, f"Airports in {country}")

        elif c == "5":
            city    = input("  🏙  City: ").strip()
            results = agent.airports_by_city(city)
            agent.print_airports_table(results, f"Airports in {city}")
            for ap in results[:3]: agent.print_airport(ap)

        elif c == "6":
            o = input("  ✈  From: ").strip()
            d = input("  ✈  To  : ").strip()
            agent.print_route(agent.route_info(o, d))

        elif c == "7":
            lat = float(input("  📍 Lat : ").strip())
            lon = float(input("  📍 Lon : ").strip())
            n   = input("  How many? [5]: ").strip()
            agent.print_airports_table(agent.nearest_airports(lat, lon, int(n) if n.isdigit() else 5),
                                       f"Nearest airports to ({lat}, {lon})")

        elif c == "8":
            o  = input("  ✈  From: ").strip()
            d  = input("  ✈  To  : ").strip()
            dt = input("  📅 Date: ").strip()
            links = agent.get_booking_links(o, d, dt)
            print()
            for site, url in links.items():
                print(f"  {site:<20}: {url}")

        elif c == "9":
            s = agent.db.stats
            print(f"\n  Airports loaded : {s['total_airports']:,}")
            print(f"  Countries       : {s['countries']}")
            print(f"  With ICAO codes : {s['with_icao']:,}")
            print(f"  Source file     : {s['source_file']}")

        elif c in ("q","quit","exit"):
            print("\n  ✈️  FlightAgent signing off!\n"); break

        else:
            print("  ⚠  Invalid option.")


if __name__ == "__main__":
    run_cli()