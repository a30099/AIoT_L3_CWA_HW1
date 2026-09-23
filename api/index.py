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


def load_all_records():
    """優先自 weather_cleaned.json 讀取，若不存在則自 SQLite data.db 查詢"""
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
