"""
parse_weather.py - Gate 2: 分析 JSON，提取氣溫與濕度資料 (資料清洗與正規化)

評分重點：
1. 提取正確 (10%)：精確解析氣溫、濕度、分區名稱與觀測時間
2. 數據完整 (5%)：過濾 -99, -999, NA 等無效異常代碼
3. 程式品質 (5%)：模組化函數設計，提供 Gate 3 database.py 串接
"""

import json
import os
import sys

# 異常代碼排除集合 (依據規格書第 10 節規範)
INVALID_VALUES = {"", "X", "NA", "null", "None", "-99", "-999", "-99.0", "-999.0"}

# 臺灣縣市歸屬六大分區對照表 (對應老師作業規格：北部、中部、南部、東北部、東部、東南部)
COUNTY_TO_REGION = {
    # 北部地區
    "基隆市": "北部地區", "臺北市": "北部地區", "新北市": "北部地區",
    "桃園市": "北部地區", "新竹市": "北部地區", "新竹縣": "北部地區", "苗栗縣": "北部地區",
    # 中部地區
    "臺中市": "中部地區", "彰化縣": "中部地區", "南投縣": "中部地區", "雲林縣": "中部地區",
    # 南部地區
    "嘉義市": "南部地區", "嘉義縣": "南部地區", "臺南市": "南部地區", "高雄市": "南部地區", "屏東縣": "南部地區",
    # 東北部地區
    "宜蘭縣": "東北部地區",
    # 東部地區
    "花蓮縣": "東部地區",
    # 東南部地區
    "臺東縣": "東南部地區",
    # 離島地區 (亦納入對照)
    "澎湖縣": "離島地區", "金門縣": "離島地區", "連江縣": "離島地區"
}


def clean_float(value, min_val=None, max_val=None):
    """資料清洗輔助函數：將字串轉換為浮點數，並檢查異常值與物理合理範圍"""
    if value is None:
        return None
    
    val_str = str(value).strip()
    if val_str in INVALID_VALUES:
        return None
    
    try:
        num = float(val_str)
        # 範圍檢查
        if min_val is not None and num < min_val:
            return None
        if max_val is not None and num > max_val:
            return None
        return num
    except (ValueError, TypeError):
        return None


def parse_weather_data(raw_file="weather_raw.json", output_file="weather_cleaned.json"):
    """
    解析 Gate 1 儲存之原始 JSON 資料
    提取：測站名稱、分區、縣市、經緯度、觀測時間、氣溫、相對濕度、當日最高/最低溫
    """
    if not os.path.exists(raw_file):
        print(f"[錯誤] 找不到原始資料檔 {raw_file}！請先執行 python fetch_weather.py")
        sys.exit(1)

    print(f"[資訊] 讀取原始資料檔: {raw_file}")
    with open(raw_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    stations = data.get("records", {}).get("Station", [])
    if not stations:
        print("[警告] 資料集中無任何測站資料 (Station 清單為空)！")
        return []

    cleaned_records = []
    dropped_count = 0

    for st in stations:
        st_id = st.get("StationId")
        st_name = st.get("StationName")
        
        # 1. 取得地理與縣市資訊
        geo_info = st.get("GeoInfo", {})
        county = geo_info.get("CountyName", "").replace("台", "臺")
        town = geo_info.get("TownName", "")
        region = COUNTY_TO_REGION.get(county, "其他分區")

        # 座標解析 (優先取 WGS84，若無則取第一組)
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

        # 2. 取得時間
        obs_time_raw = st.get("ObsTime", {}).get("DateTime", "")
        obs_date = obs_time_raw.split("T")[0] if "T" in obs_time_raw else obs_time_raw[:10]

        # 3. 提取天氣要素 (氣溫與相對濕度)
        we = st.get("WeatherElement", {})
        temp = clean_float(we.get("AirTemperature"), min_val=-20.0, max_val=50.0)
        humidity = clean_float(we.get("RelativeHumidity"), min_val=0.0, max_val=100.0)

        # 4. 當日極值 (最高溫與最低溫)
        daily_extreme = we.get("DailyExtreme", {})
        max_t = clean_float(daily_extreme.get("DailyHigh", {}).get("TemperatureInfo", {}).get("AirTemperature"))
        min_t = clean_float(daily_extreme.get("DailyLow", {}).get("TemperatureInfo", {}).get("AirTemperature"))

        # 若無極值記錄，則暫以當前觀測溫作為基準
        if max_t is None and temp is not None:
            max_t = temp
        if min_t is None and temp is not None:
            min_t = temp

        # 5. 檢核過濾漏斗：缺少測站名稱、氣溫、濕度或經緯度者剔除
        if not st_id or not st_name or temp is None or humidity is None or lat is None or lon is None:
            dropped_count += 1
            continue

        record = {
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
        }
        cleaned_records.append(record)

    # 6. 將清洗後結果存為 JSON 檔
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(cleaned_records, f, ensure_ascii=False, indent=2)

    # 7. 印出統計摘要報告
    print("\n" + "="*55)
    print("【Gate 2 資料清洗與正規化統計報告】")
    print(f"  • 原始總測站數: {len(stations)} 站")
    print(f"  • 有效完整測站數: {len(cleaned_records)} 站")
    print(f"  • 剔除異常/缺漏站數: {dropped_count} 站")
    print("="*55)

    # 各分區測站數量統計
    region_stats = {}
    for r in cleaned_records:
        reg = r["region_name"]
        region_stats[reg] = region_stats.get(reg, 0) + 1
    
    print("\n[六大分區有效測站分佈]:")
    for reg, cnt in sorted(region_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  • {reg}: {cnt} 個測站")

    # 預覽前 3 筆清洗後之樣本
    print("\n[清洗後資料樣本預覽 (前 3 筆)]:")
    print(f"{'分區':<8} {'縣市':<6} {'測站名稱':<8} {'氣溫(°C)':<10} {'濕度(%)':<10} {'觀測時間'}")
    print("-" * 65)
    for item in cleaned_records[:3]:
        print(f"{item['region_name']:<8} {item['county_name']:<6} {item['station_name']:<8} {item['temperature']:<10} {item['humidity']:<10} {item['obs_time']}")
    print("-" * 65)
    print(f"[完成] 乾淨資料已存入: {output_file}\n")

    return cleaned_records


if __name__ == "__main__":
    parse_weather_data()
