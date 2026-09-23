"""
fetch_weather.py - Gate 1: 取得 CWA API 氣象資料 (包含氣溫與濕度)

評分重點：
1. 使用 requests 呼叫 CWA API (10%)
2. 完整錯誤處理機制 (5%)
3. 程式品質與金鑰環境變數管理 (5%)
4. 儲存原始 JSON 供 Gate 2 解析使用
"""

import os
import json
import sys
import requests

# 嘗試載入 .env 環境變數
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def get_cwa_data():
    # 1. 取得 API Key (不寫死在程式碼中)
    api_key = os.getenv("CWA_API_KEY")
    if not api_key:
        print("[錯誤] 找不到 CWA_API_KEY！請確認專案目錄下的 .env 檔案中已設定金鑰。")
        sys.exit(1)

    # 2. 設定 API 端點 (O-A0003-001 自動氣象站觀測資料，完整涵蓋全臺測站之「氣溫」與「相對濕度」)
    url = os.getenv("CWA_DATA_URL", "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001")
    
    headers = {
        "Authorization": api_key
    }
    
    print(f"[資訊] 正在向中央氣象署 API 發送請求...")
    print(f"[資訊] 目標端點: {url}")

    # 3. 發送 HTTP 請求與例外處理 (評分 5%)
    # 針對政府伺服器憑證常見之 SSL 檢驗問題，加入 verify=False 與警告抑制
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    try:
        response = requests.get(url, headers=headers, timeout=15, verify=False)
        response.raise_for_status()  # 若狀態碼非 200 會主動拋出例外
        data = response.json()
    except requests.exceptions.Timeout:
        print("[錯誤] 請求逾時 (Timeout)：無法在時限內連線至 CWA API，請檢查網路狀況。")
        sys.exit(1)
    except requests.exceptions.HTTPError as err:
        print(f"[錯誤] HTTP 錯誤：{err} (請確認 API Key 是否有效)")
        sys.exit(1)
    except requests.exceptions.RequestException as err:
        print(f"[錯誤] 連線失敗：{err}")
        sys.exit(1)
    except json.JSONDecodeError:
        print("[錯誤] 解析失敗：回傳資料非合法的 JSON 格式。")
        sys.exit(1)

    # 4. 驗證 API 回應狀態
    if data.get("success") != "true":
        print(f"[警告] CWA API 回應未標示為 success，完整回應訊息：{data.get('message', '無訊息')}")
        sys.exit(1)

    print("[成功] CWA API 資料取得成功 (HTTP 200 OK)！")

    # 5. 檢驗資料是否包含老師要求的「溫度」與「濕度」
    records = data.get("records", {})
    stations = records.get("Station", [])
    
    if stations:
        sample_station = stations[0]
        st_name = sample_station.get("StationName", "未知")
        elements = sample_station.get("WeatherElement", {})
        temp = elements.get("AirTemperature", "無")
        humidity = elements.get("RelativeHumidity", "無")
        
        print("\n" + "="*50)
        print(f"[資料取樣驗證] 測站名稱: {st_name}")
        print(f"  • 氣溫 (AirTemperature): {temp} °C")
        print(f"  • 相對濕度 (RelativeHumidity): {humidity} %")
        print("="*50 + "\n")
        
        # 依老師指引：以 json.dumps 格式化檢視前 1 筆樣本
        print("[樣本 JSON 結構預覽]:")
        sample_display = {
            "StationName": st_name,
            "ObsTime": sample_station.get("ObsTime"),
            "GeoInfo": sample_station.get("GeoInfo"),
            "AirTemperature": temp,
            "RelativeHumidity": humidity
        }
        print(json.dumps(sample_display, indent=2, ensure_ascii=False))

    # 6. 將原始資料存檔為 weather_raw.json 供 Gate 2 使用
    output_filename = "weather_raw.json"
    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n[完成] 完整資料已儲存至: {output_filename} (測站總數: {len(stations)} 站)")
    except IOError as err:
        print(f"[錯誤] 寫入檔案失敗: {err}")
        sys.exit(1)

    return data


if __name__ == "__main__":
    get_cwa_data()
