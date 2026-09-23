"""
database.py - Gate 3: 存入 SQLite 資料庫與查詢檢驗 (包含氣溫與濕度)

評分重點：
1. 儲存資料 (10%)：建立 data.db 與 TemperatureForecasts 資料表，批次寫入結構化氣象資料
2. 查詢檢驗 (5%)：
   - 驗證查詢 ①：SELECT DISTINCT regionName FROM TemperatureForecasts;
   - 驗證查詢 ②：SELECT * FROM TemperatureForecasts WHERE regionName = '中部地區';
3. 程式品質 (5%)：模組化函數封裝，提供 Gate 4 Streamlit app.py 快速呼叫
"""

import sqlite3
import json
import os
import sys

# 資料庫預設檔名 (嚴格依據老師指定名稱: data.db)
DB_PATH = "data.db"
CLEANED_DATA_PATH = "weather_cleaned.json"


def get_db_connection(db_path=DB_PATH):
    """建立資料庫連線並啟用欄位名稱存取"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=DB_PATH):
    """
    初始化 SQLite 資料庫與建立資料表
    包含老師規定的基本欄位 (id, regionName, dataDate, minT, maxT)
    以及老師特別要求的「氣溫 (temperature)」與「濕度 (humidity)」
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS TemperatureForecasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        stationId TEXT,
        stationName TEXT,
        regionName TEXT NOT NULL,
        countyName TEXT,
        townName TEXT,
        dataDate TEXT NOT NULL,
        obsTime TEXT,
        temperature REAL NOT NULL,
        humidity REAL NOT NULL,
        minT REAL,
        maxT REAL,
        lat REAL,
        lon REAL
    );
    """)
    conn.commit()
    conn.close()
    print(f"[資訊] 資料表 TemperatureForecasts 初始化完成 (資料庫: {db_path})")


def save_weather_to_db(records, db_path=DB_PATH):
    """將清洗後的氣象資料批次存入 SQLite 資料庫"""
    if not records:
        print("[警告] 無任何資料可寫入資料庫！")
        return 0

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # 寫入前先清空舊有資料，確保每次執行為最新快照且不重複累積
    cursor.execute("DELETE FROM TemperatureForecasts;")

    sql = """
    INSERT INTO TemperatureForecasts (
        stationId, stationName, regionName, countyName, townName,
        dataDate, obsTime, temperature, humidity, minT, maxT, lat, lon
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """

    data_tuples = [
        (
            r["station_id"],
            r["station_name"],
            r["region_name"],
            r["county_name"],
            r["town_name"],
            r["data_date"],
            r["obs_time"],
            r["temperature"],
            r["humidity"],
            r["min_t"],
            r["max_t"],
            r["lat"],
            r["lon"]
        )
        for r in records
    ]

    cursor.executemany(sql, data_tuples)
    conn.commit()
    inserted_count = cursor.rowcount
    conn.close()

    print(f"[成功] 成功將 {len(data_tuples)} 筆測站氣象觀測數據寫入資料庫 {db_path}！")
    return inserted_count


def verify_queries(db_path=DB_PATH):
    """
    執行老師指定之兩大驗證 SQL 查詢 (評分 5%)
    1. SELECT DISTINCT regionName FROM TemperatureForecasts;
    2. SELECT * FROM TemperatureForecasts WHERE regionName = '中部地區';
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    print("\n" + "="*60)
    print("【Gate 3 驗證查詢 ①：列出所有分區名稱】")
    print("SQL: SELECT DISTINCT regionName FROM TemperatureForecasts;")
    cursor.execute("SELECT DISTINCT regionName FROM TemperatureForecasts ORDER BY regionName;")
    regions = [row["regionName"] for row in cursor.fetchall()]
    print(f"查詢結果: {regions}")
    print("="*60)

    print("\n" + "="*60)
    print("【Gate 3 驗證查詢 ②：查詢中部地區資料 (前 5 筆)】")
    print("SQL: SELECT * FROM TemperatureForecasts WHERE regionName = '中部地區' LIMIT 5;")
    cursor.execute("""
        SELECT stationName, countyName, dataDate, temperature, humidity, minT, maxT 
        FROM TemperatureForecasts 
        WHERE regionName = '中部地區' 
        LIMIT 5;
    """)
    rows = cursor.fetchall()
    print(f"{'測站名稱':<8} {'縣市':<6} {'日期':<12} {'氣溫(°C)':<10} {'濕度(%)':<10} {'最低溫':<8} {'最高溫'}")
    print("-" * 65)
    for r in rows:
        print(f"{r['stationName']:<8} {r['countyName']:<6} {r['dataDate']:<12} {r['temperature']:<10} {r['humidity']:<10} {r['minT']:<8} {r['maxT']}")
    print("="*60)

    # 額外統計：各分區測站數、平均氣溫與平均濕度
    print("\n" + "="*60)
    print("【Gate 3 額外驗證：各分區氣溫與濕度統計摘要】")
    cursor.execute("""
        SELECT 
            regionName, 
            COUNT(*) as stationCount,
            ROUND(AVG(temperature), 1) as avgTemp,
            ROUND(AVG(humidity), 1) as avgHumidity,
            MIN(minT) as regionMinT,
            MAX(maxT) as regionMaxT
        FROM TemperatureForecasts
        GROUP BY regionName
        ORDER BY stationCount DESC;
    """)
    stats = cursor.fetchall()
    print(f"{'分區名稱':<8} {'測站數':<8} {'平均氣溫(°C)':<14} {'平均濕度(%)':<14} {'分區最低~最高溫'}")
    print("-" * 65)
    for s in stats:
        print(f"{s['regionName']:<8} {s['stationCount']:<8} {s['avgTemp']:<14} {s['avgHumidity']:<14} {s['regionMinT']} ~ {s['regionMaxT']} °C")
    print("="*60 + "\n")

    conn.close()


def main():
    # 1. 確保清洗後之資料存在
    if not os.path.exists(CLEANED_DATA_PATH):
        print(f"[資訊] 找不到 {CLEANED_DATA_PATH}，嘗試自動執行 parse_weather.py 解析原始資料...")
        try:
            from parse_weather import parse_weather_data
            records = parse_weather_data()
        except Exception as e:
            print(f"[錯誤] 解析資料失敗: {e}")
            sys.exit(1)
    else:
        with open(CLEANED_DATA_PATH, "r", encoding="utf-8") as f:
            records = json.load(f)

    # 2. 初始化資料表
    init_db()

    # 3. 存入 SQLite 資料庫 (評分 10%)
    save_weather_to_db(records)

    # 4. 執行驗證查詢 (評分 5%)
    verify_queries()


if __name__ == "__main__":
    main()
