"""
app.py - Gate 4: Streamlit 互動式天氣預報與觀測 Web App

評分重點：
1. 下拉式選單選擇地區 (10%)
2. 折線圖與數據表格 (15%)
3. 使用 SQL 從 SQLite (data.db) 查詢資料，不可於前端呼叫 API (10%)
4. 程式品質與互動體驗 (5%)
5. [Bonus 加分項] 互動式臺灣地圖視覺化 (Folium 氣溫色階地圖)
"""

import sqlite3
import os
import pandas as pd
import streamlit as st

# 嘗試載入 folium 相關套件 (加分項)
try:
    import folium
    from streamlit_folium import st_folium
    HAS_FOLIUM = True
except ImportError:
    HAS_FOLIUM = False

# 頁面基本設定
st.set_page_config(
    page_title="臺灣氣候觀測儀表板 - CWA x SQLite x Streamlit",
    page_icon="🌤️",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_PATH = "data.db"


def check_and_prepare_db():
    """檢查本地 SQLite 是否存在，若無則自動進行 Gate 1~3 管道建立"""
    if not os.path.exists(DB_PATH):
        st.warning("⚠️ 尚未偵測到本地資料庫 data.db，正在自動執行資料初始化...")
        from database import main as db_main
        db_main()
        st.success("✅ 資料庫初始化完成！")


@st.cache_data(ttl=60)
def load_regions():
    """從 SQLite 查詢所有不重複的分區名稱"""
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT DISTINCT regionName FROM TemperatureForecasts ORDER BY regionName;"
    regions = pd.read_sql_query(query, conn)["regionName"].tolist()
    conn.close()
    return regions


def load_weather_data(region_name=None):
    """嚴格遵循規定：使用 SQL 從本地 SQLite data.db 查詢數據"""
    conn = sqlite3.connect(DB_PATH)
    if not region_name or region_name == "全臺總覽":
        query = """
        SELECT stationId, stationName, regionName, countyName, townName,
               dataDate, obsTime, temperature, humidity, minT, maxT, lat, lon
        FROM TemperatureForecasts
        ORDER BY temperature DESC;
        """
        df = pd.read_sql_query(query, conn)
    else:
        query = """
        SELECT stationId, stationName, regionName, countyName, townName,
               dataDate, obsTime, temperature, humidity, minT, maxT, lat, lon
        FROM TemperatureForecasts
        WHERE regionName = ?
        ORDER BY temperature DESC;
        """
        df = pd.read_sql_query(query, conn, params=(region_name,))
    conn.close()
    return df


def get_temperature_color(temp):
    """依據老師投影片色階規範回傳對應顏色代碼"""
    if temp < 20.0:
        return "#3182ce", "藍色 (<20°C 涼冷)"
    elif 20.0 <= temp < 25.0:
        return "#38a169", "綠色 (20-25°C 舒適)"
    elif 25.0 <= temp <= 30.0:
        return "#d69e2e", "黃色 (25-30°C 偏暖)"
    else:
        return "#e53e3e", "紅色 (>30°C 炎熱)"


# 確保資料庫就緒
check_and_prepare_db()

# ==================== 側邊欄控制項 ====================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/1/12/Central_Weather_Administration_Logo.svg/200px-Central_Weather_Administration_Logo.svg.png", width=110)
    st.title("氣象觀測設定")
    st.markdown("**HW10: CWA API x SQLite x Streamlit**")
    st.markdown("---")

    # 1. 下拉式選單選擇地區 (評分 10%)
    available_regions = load_regions()
    region_options = ["全臺總覽"] + available_regions
    selected_region = st.selectbox(
        "📍 請選擇欲瀏覽地區 (Region):",
        options=region_options,
        index=0
    )

    st.markdown("---")
    st.markdown("### 🗄️ 資料庫狀態")
    st.caption(f"資料來源：本地 SQLite (`{DB_PATH}`)")
    st.caption("連線模式：唯讀查詢 (Read-only SQL Query)")

    # 手動更新按鈕
    if st.button("🔄 立即重新拉取氣象署資料"):
        with st.spinner("正在向中央氣象署 API 同步最新觀測數據..."):
            try:
                from fetch_weather import get_cwa_data
                from parse_weather import parse_weather_data
                from database import save_weather_to_db

                raw = get_cwa_data()
                cleaned = parse_weather_data()
                save_weather_to_db(cleaned)
                st.cache_data.clear()
                st.success("✅ 資料庫更新完成！")
                st.rerun()
            except Exception as e:
                st.error(f"❌ 更新失敗: {e}")

    st.markdown("---")
    st.markdown("👨‍💻 開發者：`a30099`  \n📧 `a30099a30099@gmail.com`")


# ==================== 主頁面呈現 ====================
st.title("🌤️ 臺灣即時氣象預報與觀測儀表板")
st.markdown(f"目前顯示區域：**{selected_region}** ｜ 資料涵蓋：**即時氣溫、相對濕度與極值分佈**")

# 撈取目前選取的數據 (SQL 查詢)
df = load_weather_data(selected_region)

if df.empty:
    st.warning("⚠️ 目前選取的區域無資料。")
    st.stop()

# 觀測時間資訊
latest_obs_time = df["obsTime"].iloc[0] if "obsTime" in df.columns and not df.empty else "未知"
st.caption(f"🕒 氣象署最後觀測時間戳記：`{latest_obs_time}`")

# 2. 核心指標卡片 (Metric Cards)
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("📊 觀測測站數", f"{len(df)} 站")
with col2:
    avg_temp = df["temperature"].mean()
    st.metric("🌡️ 平均氣溫", f"{avg_temp:.1f} °C")
with col3:
    avg_hum = df["humidity"].mean()
    st.metric("💧 平均相對濕度", f"{avg_hum:.1f} %")
with col4:
    hottest_station = df.loc[df["temperature"].idxmax()]
    st.metric("🔥 該區最高溫", f"{hottest_station['temperature']} °C", f"{hottest_station['stationName']}")

st.markdown("---")

# 3. 分頁結構設計 (圖表、表格、地圖加分項)
tab_charts, tab_table, tab_map = st.tabs(["📈 氣溫與濕度圖表分析", "📋 測站詳細數據清單", "🗺️ 臺灣地圖視覺化 (Bonus)"])

# ==================== Tab 1: 折線圖與圖表分析 (評分 15%) ====================
with tab_charts:
    st.subheader(f"📊 {selected_region} 測站氣溫走勢與分佈")

    # 氣溫走勢圖 (即時氣溫, 最低溫, 最高溫)
    chart_data = df.copy()
    if len(chart_data) > 30 and selected_region == "全臺總覽":
        chart_data = chart_data.head(30)
        st.info("💡 全臺測站較多，圖表展示目前氣溫最高之前 30 個指標測站：")

    chart_display_df = chart_data.set_index("stationName")[["temperature", "minT", "maxT"]]
    chart_display_df.columns = ["即時氣溫 (°C)", "最低溫 (°C)", "最高溫 (°C)"]

    st.line_chart(chart_display_df, height=350)

    # 濕度長條分佈圖 (滿足老師「溫度+濕度」要求)
    st.subheader(f"💧 {selected_region} 相對濕度分析 (%)")
    humidity_df = chart_data.set_index("stationName")[["humidity"]]
    humidity_df.columns = ["相對濕度 (%)"]
    st.bar_chart(humidity_df, height=260)


# ==================== Tab 2: 詳細數據表格 (評分 15%) ====================
with tab_table:
    st.subheader(f"📋 {selected_region} 測站完整數據列表")
    
    # 搜尋過濾功能
    search_keyword = st.text_input("🔍 搜尋特定測站名稱或所屬縣市：", "")
    display_table = df.copy()
    if search_keyword:
        display_table = display_table[
            display_table["stationName"].str.contains(search_keyword, na=False) |
            display_table["countyName"].str.contains(search_keyword, na=False)
        ]

    # 美化欄位名稱顯示
    columns_map = {
        "stationId": "測站代碼",
        "stationName": "測站名稱",
        "regionName": "地理分區",
        "countyName": "所屬縣市",
        "townName": "鄉鎮區",
        "temperature": "即時氣溫 (°C)",
        "humidity": "相對濕度 (%)",
        "minT": "當日最低溫 (°C)",
        "maxT": "當日最高溫 (°C)",
        "obsTime": "觀測時間"
    }
    
    show_cols = [c for c in columns_map.keys() if c in display_table.columns]
    formatted_df = display_table[show_cols].rename(columns=columns_map)

    st.dataframe(
        formatted_df,
        width="stretch",
        hide_index=True,
        height=450
    )

    # 提供 CSV 下載
    csv = formatted_df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        label="📥 下載此區域觀測數據 (CSV)",
        data=csv,
        file_name=f"cwa_weather_{selected_region}.csv",
        mime="text/csv"
    )


def load_region_summary():
    """從 SQLite 計算六大分區之中心座標、平均氣溫、平均濕度、最低/最高溫與測站數"""
    conn = sqlite3.connect(DB_PATH)
    query = """
    SELECT 
        regionName,
        AVG(lat) as centerLat,
        AVG(lon) as centerLon,
        ROUND(AVG(temperature), 1) as avgTemp,
        ROUND(AVG(humidity), 1) as avgHumidity,
        ROUND(MIN(minT), 1) as minT,
        ROUND(MAX(maxT), 1) as maxT,
        COUNT(*) as stationCount,
        MAX(dataDate) as dataDate
    FROM TemperatureForecasts
    GROUP BY regionName
    ORDER BY avgTemp DESC;
    """
    df_summary = pd.read_sql_query(query, conn)
    conn.close()
    return df_summary


# ==================== Tab 3: 臺灣地圖視覺化 (Gate 5 加分項) ====================
with tab_map:
    st.subheader("🗺️ 臺灣各區互動式氣象地圖 (Gate 5 進階加分項)")
    st.markdown("""
    **溫度色階指標規範**：  
    🔵 **藍色**：`< 20°C` (涼冷) ｜ 🟢 **綠色**：`20°C – 25°C` (舒適) ｜ 🟡 **黃色**：`25°C – 30°C` (偏暖) ｜ 🔴 **紅色**：`> 30°C` (炎熱)
    """)

    if not HAS_FOLIUM:
        st.warning("⚠️ 尚未偵測到 `folium` 套件，地圖功能暫不可用。")
    else:
        # 切換顯示層級
        map_mode = st.radio(
            "📍 請選擇地圖顯示層級：",
            options=["六大分區平均氣溫總覽 (老師投影片標準樣式)", "當前選取區域測站詳細標記"],
            horizontal=True
        )

        if map_mode == "六大分區平均氣溫總覽 (老師投影片標準樣式)":
            df_regions = load_region_summary()
            
            # 以臺灣中心為基準
            m = folium.Map(
                location=[23.7, 121.0],
                zoom_start=7,
                tiles="OpenStreetMap"
            )

            for _, r in df_regions.iterrows():
                color, label = get_temperature_color(r["avgTemp"])
                
                # 投影片風格 Popup 卡片
                popup_html = f"""
                <div style="font-family: sans-serif; font-size: 13px; line-height: 1.6; min-width: 170px;">
                    <h4 style="margin: 0 0 6px 0; color: #2b6cb0; border-bottom: 2px solid #e2e8f0; padding-bottom: 4px;">{r['regionName']}</h4>
                    📅 <b>日期</b>: {r['dataDate']}<br/>
                    🌡️ <b>平均溫度</b>: <span style="color: {color}; font-size: 15px; font-weight: bold;">{r['avgTemp']} °C</span><br/>
                    💧 <b>平均濕度</b>: {r['avgHumidity']} %<br/>
                    📉 <b>最低溫 (Min)</b>: {r['minT']} °C<br/>
                    📈 <b>最高溫 (Max)</b>: {r['maxT']} °C<br/>
                    📊 <b>觀測站數</b>: {r['stationCount']} 站
                </div>
                """

                # 繪製區域代表性大圓標記
                folium.CircleMarker(
                    location=[r["centerLat"], r["centerLon"]],
                    radius=16,
                    popup=folium.Popup(popup_html, max_width=260),
                    tooltip=f"{r['regionName']}: 平均溫 {r['avgTemp']}°C (點擊查看詳細)",
                    color="#ffffff",
                    weight=2,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.9
                ).add_to(m)

                # 在地圖標記旁顯示分區名稱與平均溫度標籤
                folium.Marker(
                    location=[r["centerLat"], r["centerLon"]],
                    icon=folium.DivIcon(
                        icon_size=(100, 30),
                        icon_anchor=(50, -10),
                        html=f'<div style="font-size: 12px; font-weight: bold; color: #1a202c; text-shadow: 1px 1px 2px white; text-align: center;">{r["regionName"]}<br><span style="color:{color};">{r["avgTemp"]}°C</span></div>'
                    )
                ).add_to(m)

            st_folium(m, width="stretch", height=560)

            # 額外附帶六大分區平均氣象數據一覽表
            st.markdown("#### 📊 全臺各分區平均氣象數據一覽表")
            summary_display = df_regions[["regionName", "stationCount", "avgTemp", "avgHumidity", "minT", "maxT"]].rename(
                columns={
                    "regionName": "地理分區",
                    "stationCount": "測站數量",
                    "avgTemp": "平均氣溫 (°C)",
                    "avgHumidity": "平均相對濕度 (%)",
                    "minT": "分區最低溫 (°C)",
                    "maxT": "分區最高溫 (°C)"
                }
            )
            st.dataframe(summary_display, width="stretch", hide_index=True)

        else:
            # 當前選取區域測站詳細標記模式
            center_lat = df["lat"].mean() if not df.empty else 23.7
            center_lon = df["lon"].mean() if not df.empty else 121.0
            zoom_level = 8 if selected_region != "全臺總覽" else 7

            m = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=zoom_level,
                tiles="OpenStreetMap"
            )

            for _, row in df.iterrows():
                if pd.isna(row["lat"]) or pd.isna(row["lon"]):
                    continue

                color, label = get_temperature_color(row["temperature"])

                popup_html = f"""
                <div style="font-family: sans-serif; font-size: 13px; line-height: 1.5; min-width: 150px;">
                    <b style="font-size: 15px; color: #2b6cb0;">{row['stationName']}</b> ({row['countyName']} {row['townName']})<br/>
                    <hr style="margin: 4px 0;"/>
                    🌡️ <b>即時氣溫</b>: <span style="color: {color}; font-weight: bold;">{row['temperature']} °C</span><br/>
                    💧 <b>相對濕度</b>: {row['humidity']} %<br/>
                    📉 <b>最低/最高</b>: {row['minT']} ~ {row['maxT']} °C<br/>
                    🕒 <b>觀測時間</b>: {row['obsTime']}<br/>
                </div>
                """

                folium.CircleMarker(
                    location=[row["lat"], row["lon"]],
                    radius=7,
                    popup=folium.Popup(popup_html, max_width=250),
                    tooltip=f"{row['stationName']}: {row['temperature']}°C / {row['humidity']}%",
                    color="#ffffff",
                    weight=1,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.85
                ).add_to(m)

            st_folium(m, width="stretch", height=560)
