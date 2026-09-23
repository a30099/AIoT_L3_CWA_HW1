"""
api/index.py - Vercel Serverless Function (FastAPI 后端服務)
提供全臺氣象站即時氣溫與濕度查詢、六大分區統計與健康檢查端點。
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import json
import os
import sqlite3

app = FastAPI(
    title="CWA Weather Forecast & Temperature API",
    description="中央氣象署全臺氣象觀測與氣溫/濕度 API (Vercel Serverless)",
    version="1.0.0"
)

# 啟用 CORS 跨域請求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(BASE_DIR, "weather_cleaned.json")
DB_PATH = os.path.join(BASE_DIR, "data.db")

# 全域記憶體快取
LIVE_CACHE = {
    "stations": None,
    "last_sync": None
}

def fetch_live_cwa_data():
    """直接向 CWA API 抓取並即時清洗最新資料"""
    import urllib.request
    import ssl
    
    api_key = os.getenv("CWA_API_KEY", "CWA-C6BED603-E999-4639-B11C-67142ED3C8D6")
    url = os.getenv("CWA_DATA_URL", "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001")
    
    req = urllib.request.Request(url, headers={"Authorization": api_key})
    ctx = ssl._create_unverified_context()
    
    with urllib.request.urlopen(req, context=ctx, timeout=15) as res:
        data = json.loads(res.read().decode("utf-8"))
    
    # 即時清洗
    stations = data.get("records", {}).get("Station", [])
    from parse_weather import COUNTY_TO_REGION, clean_float
    
    cleaned = []
    for st in stations:
        st_id = st.get("StationId")
        st_name = st.get("StationName")
        geo_info = st.get("GeoInfo", {})
        county = geo_info.get("CountyName", "").replace("台", "臺")
        town = geo_info.get("TownName", "")
        region = COUNTY_TO_REGION.get(county, "其他分區")

        coords = geo_info.get("Coordinates", [])
        lat, lon = None, None
        for c in coords:
            if c.get("CoordinateName") == "WGS84":
                lat = clean_float(c.get("StationLatitude"))
                lon = clean_float(c.get("StationLongitude"))
                break
        if lat is None and coords:
            lat = clean_float(coords[0].get("StationLatitude"))
            lon = clean_float(coords[0].get("StationLongitude"))

        obs_time_raw = st.get("ObsTime", {}).get("DateTime", "")
        obs_date = obs_time_raw.split("T")[0] if "T" in obs_time_raw else obs_time_raw[:10]

        we = st.get("WeatherElement", {})
        temp = clean_float(we.get("AirTemperature"), min_val=-20.0, max_val=50.0)
        humidity = clean_float(we.get("RelativeHumidity"), min_val=0.0, max_val=100.0)

        daily_extreme = we.get("DailyExtreme", {})
        max_t = clean_float(daily_extreme.get("DailyHigh", {}).get("TemperatureInfo", {}).get("AirTemperature"))
        min_t = clean_float(daily_extreme.get("DailyLow", {}).get("TemperatureInfo", {}).get("AirTemperature"))

        if max_t is None and temp is not None: max_t = temp
        if min_t is None and temp is not None: min_t = temp

        if not st_id or not st_name or temp is None or humidity is None or lat is None or lon is None:
            continue

        cleaned.append({
            "station_id": st_id,
            "station_name": st_name,
            "region_name": region,
            "county_name": county,
            "town_name": town,
            "data_date": obs_date,
            "obs_time": obs_time_raw,
            "temperature": round(temp, 1),
            "humidity": round(humidity, 1),
            "min_t": round(min_t, 1),
            "max_t": round(max_t, 1),
            "lat": lat,
            "lon": lon
        })
    
    LIVE_CACHE["stations"] = cleaned
    LIVE_CACHE["last_sync"] = obs_time_raw
    return cleaned


def load_all_records():
    """優先自即時快取讀取，若無則自 weather_cleaned.json 讀取"""
    if LIVE_CACHE["stations"]:
        return LIVE_CACHE["stations"]

    try:
        data = fetch_live_cwa_data()
        if data:
            return data
    except Exception:
        pass

    if os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT stationId as station_id, stationName as station_name, regionName as region_name,
                       countyName as county_name, townName as town_name, dataDate as data_date,
                       obsTime as obs_time, temperature, humidity, minT as min_t, maxT as max_t, lat, lon
                FROM TemperatureForecasts
                ORDER BY temperature DESC;
            """)
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception:
            pass

    return []


@app.get("/api/health")
def health_check():
    """健康狀態檢查端點"""
    records = load_all_records()
    return {
        "status": "ok",
        "service": "CWA Weather Dashboard API",
        "total_stations": len(records),
        "source": "Central Weather Administration (CWA)"
    }


@app.get("/api/regions")
def get_region_summary():
    """取得六大分區氣溫與濕度統計摘要"""
    records = load_all_records()
    if not records:
        return {"regions": []}

    grouped = {}
    for r in records:
        reg = r.get("region_name", "其他分區")
        if reg not in grouped:
            grouped[reg] = {
                "region_name": reg,
                "stations": 0,
                "temps": [],
                "hums": [],
                "lats": [],
                "lons": [],
                "data_date": r.get("data_date", "")
            }
        grouped[reg]["stations"] += 1
        if r.get("temperature") is not None:
            grouped[reg]["temps"].append(r["temperature"])
        if r.get("humidity") is not None:
            grouped[reg]["hums"].append(r["humidity"])
        if r.get("lat") is not None:
            grouped[reg]["lats"].append(r["lat"])
        if r.get("lon") is not None:
            grouped[reg]["lons"].append(r["lon"])

    result = []
    for reg, g in grouped.items():
        temps = g["temps"]
        hums = g["hums"]
        lats = g["lats"]
        lons = g["lons"]
        result.append({
            "regionName": reg,
            "stationCount": g["stations"],
            "avgTemp": round(sum(temps) / len(temps), 1) if temps else 0.0,
            "avgHumidity": round(sum(hums) / len(hums), 1) if hums else 0.0,
            "minT": min(temps) if temps else 0.0,
            "maxT": max(temps) if temps else 0.0,
            "centerLat": sum(lats) / len(lats) if lats else 23.7,
            "centerLon": sum(lons) / len(lons) if lons else 121.0,
            "dataDate": g["data_date"]
        })

    result.sort(key=lambda x: x["avgTemp"], reverse=True)
    return {"regions": result}


@app.get("/api/weather")
def get_weather(region: str | None = None):
    """取得全臺或特定分區之測站觀測資料"""
    records = load_all_records()
    if region and region != "全臺總覽":
        records = [r for r in records if r.get("region_name") == region]
    
    return {
        "count": len(records),
        "region": region or "全臺總覽",
        "stations": records
    }


@app.get("/api/sync")
@app.post("/api/sync")
def sync_weather():
    """主動向中央氣象署 CWA API 請求最新觀測資料並強制刷新快取"""
    try:
        updated = fetch_live_cwa_data()
        return {
            "status": "success",
            "message": f"成功向中央氣象署抓取最新資料！共取得 {len(updated)} 站最新氣溫與濕度。",
            "count": len(updated),
            "last_sync": LIVE_CACHE.get("last_sync")
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"同步失敗: {str(e)}，將維持現有快取資料。",
            "count": len(load_all_records())
        }

