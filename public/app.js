// =========================================================
// Taiwan CWA Weather Forecast Dashboard - Frontend Logic
// =========================================================

let allStations = [];
let allRegions = [];
let currentFilteredStations = [];
let mapInstance = null;
let markersLayerGroup = null;
let tempChart = null;
let humChart = null;

// 氣溫色階函數 (老師規範: <20藍, 20-25綠, 25-30黃, >30紅)
function getTempColor(temp) {
  if (temp < 20.0) return "#3182ce";
  if (temp < 25.0) return "#38a169";
  if (temp <= 30.0) return "#d69e2e";
  return "#e53e3e";
}

// 取得資料
async function fetchDashboardData() {
  try {
    let weatherRes = await fetch("/api/weather");
    let regionsRes = await fetch("/api/regions");

    // 若 /api 前綴被去除，嘗試備援路徑
    if (weatherRes.status === 404 || regionsRes.status === 404) {
      weatherRes = await fetch("/weather");
      regionsRes = await fetch("/regions");
    }

    if (!weatherRes.ok || !regionsRes.ok) {
      throw new Error(`API 響應異常 (HTTP ${weatherRes.status}/${regionsRes.status})`);
    }

    const weatherData = await weatherRes.json();
    const regionsData = await regionsRes.json();

    allStations = weatherData.stations || [];
    allRegions = regionsData.regions || [];

    document.getElementById("liveStatusBadge").innerHTML = '<span class="status-dot"></span> 連線正常 (Vercel API)';
  } catch (err) {
    console.warn("無法取得 API 端點資料，嘗試讀取靜態 weather_cleaned.json 備援...", err);
    try {
      const fallbackRes = await fetch("weather_cleaned.json");
      if (fallbackRes.ok) {
        allStations = await fallbackRes.json();
        computeRegionsSummary();
        document.getElementById("liveStatusBadge").innerHTML = '<span class="status-dot"></span> 離線快照模式';
      }
    } catch (e) {
      console.error("載入失敗:", e);
    }
  }

  applyFilterAndRender();
}

function computeRegionsSummary() {
  const groups = {};
  allStations.forEach(s => {
    const reg = s.region_name || "其他分區";
    if (!groups[reg]) {
      groups[reg] = { regionName: reg, stationCount: 0, temps: [], hums: [], lats: [], lons: [], dataDate: s.data_date };
    }
    groups[reg].stationCount++;
    if (s.temperature != null) groups[reg].temps.push(s.temperature);
    if (s.humidity != null) groups[reg].hums.push(s.humidity);
    if (s.lat != null) groups[reg].lats.push(s.lat);
    if (s.lon != null) groups[reg].lons.push(s.lon);
  });

  allRegions = Object.values(groups).map(g => ({
    regionName: g.regionName,
    stationCount: g.stationCount,
    avgTemp: g.temps.length ? +(g.temps.reduce((a, b) => a + b, 0) / g.temps.length).toFixed(1) : 0,
    avgHumidity: g.hums.length ? +(g.hums.reduce((a, b) => a + b, 0) / g.hums.length).toFixed(1) : 0,
    minT: g.temps.length ? Math.min(...g.temps) : 0,
    maxT: g.temps.length ? Math.max(...g.temps) : 0,
    centerLat: g.lats.length ? g.lats.reduce((a, b) => a + b, 0) / g.lats.length : 23.7,
    centerLon: g.lons.length ? g.lons.reduce((a, b) => a + b, 0) / g.lons.length : 121.0,
    dataDate: g.dataDate
  })).sort((a, b) => b.avgTemp - a.avgTemp);
}

// 篩選與渲染
function applyFilterAndRender() {
  const selectedRegion = document.getElementById("regionSelect").value;
  const keyword = document.getElementById("stationSearch").value.trim().toLowerCase();

  currentFilteredStations = allStations.filter(s => {
    const matchRegion = (selectedRegion === "全臺總覽") || (s.region_name === selectedRegion);
    const matchKeyword = !keyword || 
      (s.station_name && s.station_name.toLowerCase().includes(keyword)) ||
      (s.county_name && s.county_name.toLowerCase().includes(keyword));
    return matchRegion && matchKeyword;
  });

  renderKPIs(currentFilteredStations);
  renderMap();
  renderCharts(currentFilteredStations);
  renderTable(currentFilteredStations);
}

// 1. 渲染 KPI 卡片
function renderKPIs(stations) {
  if (!stations.length) {
    document.getElementById("stationCountVal").textContent = "0 站";
    document.getElementById("avgTempVal").textContent = "-- °C";
    document.getElementById("avgHumVal").textContent = "-- %";
    document.getElementById("hottestTempVal").textContent = "-- °C";
    document.getElementById("hottestStationVal").textContent = "--";
    return;
  }

  document.getElementById("stationCountVal").textContent = `${stations.length} 站`;

  const validTemps = stations.map(s => s.temperature).filter(t => t != null);
  const validHums = stations.map(s => s.humidity).filter(h => h != null);

  const avgTemp = validTemps.length ? (validTemps.reduce((a, b) => a + b, 0) / validTemps.length).toFixed(1) : "--";
  const avgHum = validHums.length ? (validHums.reduce((a, b) => a + b, 0) / validHums.length).toFixed(1) : "--";

  document.getElementById("avgTempVal").textContent = `${avgTemp} °C`;
  document.getElementById("avgHumVal").textContent = `${avgHum} %`;

  // 最高溫測站
  const hottest = stations.reduce((max, s) => (s.temperature > (max.temperature || -999)) ? s : max, stations[0]);
  if (hottest && hottest.temperature != null) {
    document.getElementById("hottestTempVal").textContent = `${hottest.temperature} °C`;
    document.getElementById("hottestStationVal").textContent = `${hottest.station_name} (${hottest.county_name || ''})`;
  }

  // 觀測時間
  if (stations[0] && stations[0].obs_time) {
    document.getElementById("obsTimeDisplay").textContent = `最後觀測：${stations[0].obs_time}`;
  }
}

// 2. 渲染 Leaflet 地圖 (Gate 5)
function renderMap() {
  if (!mapInstance) {
    mapInstance = L.map("taiwanMap").setView([23.7, 121.0], 7);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(mapInstance);
    markersLayerGroup = L.layerGroup().addTo(mapInstance);
  }

  markersLayerGroup.clearLayers();
  const mode = document.querySelector('input[name="mapMode"]:checked').value;

  if (mode === "regions") {
    // 六大分區平均總覽模式 (老師樣式)
    allRegions.forEach(r => {
      const color = getTempColor(r.avgTemp);
      const popupHtml = `
        <div style="font-size: 13px; line-height: 1.6; min-width: 170px;">
          <h4 style="margin: 0 0 6px 0; color: #2563eb; border-bottom: 2px solid #e2e8f0; padding-bottom: 4px;">${r.regionName}</h4>
          📅 <b>觀測日期</b>: ${r.dataDate}<br/>
          🌡️ <b>平均溫度</b>: <span style="color: ${color}; font-size: 15px; font-weight: bold;">${r.avgTemp} °C</span><br/>
          💧 <b>平均濕度</b>: ${r.avgHumidity} %<br/>
          📉 <b>最低溫 (Min)</b>: ${r.minT} °C<br/>
          📈 <b>最高溫 (Max)</b>: ${r.maxT} °C<br/>
          📊 <b>測站總數</b>: ${r.stationCount} 站
        </div>
      `;

      L.circleMarker([r.centerLat, r.centerLon], {
        radius: 18,
        color: "#ffffff",
        weight: 2,
        fillColor: color,
        fillOpacity: 0.9
      })
      .bindPopup(popupHtml)
      .bindTooltip(`${r.regionName}: ${r.avgTemp}°C`, { direction: "top" })
      .addTo(markersLayerGroup);

      // 文字標籤
      L.marker([r.centerLat, r.centerLon], {
        icon: L.divIcon({
          className: "custom-div-icon",
          html: `<div style="font-size: 12px; font-weight: bold; color: #0f172a; text-shadow: 1px 1px 2px white; text-align: center; margin-top: 18px;">${r.regionName}<br><span style="color:${color}">${r.avgTemp}°C</span></div>`,
          iconSize: [80, 30],
          iconAnchor: [40, 0]
        })
      }).addTo(markersLayerGroup);
    });

    mapInstance.setView([23.7, 121.0], 7);
  } else {
    // 測站詳細點標記模式
    currentFilteredStations.forEach(s => {
      if (s.lat == null || s.lon == null) return;

      const color = getTempColor(s.temperature);
      const popupHtml = `
        <div style="font-size: 13px; line-height: 1.5; min-width: 150px;">
          <b style="font-size: 15px; color: #2563eb;">${s.station_name}</b> (${s.county_name || ''} ${s.town_name || ''})<br/>
          <hr style="margin: 4px 0; border: none; border-top: 1px solid #e2e8f0;"/>
          🌡️ <b>即時氣溫</b>: <span style="color: ${color}; font-weight: bold;">${s.temperature} °C</span><br/>
          💧 <b>相對濕度</b>: ${s.humidity} %<br/>
          📉 <b>最低/最高</b>: ${s.min_t} ~ ${s.max_t} °C<br/>
          🕒 <b>觀測時間</b>: ${s.obs_time}
        </div>
      `;

      L.circleMarker([s.lat, s.lon], {
        radius: 7,
        color: "#ffffff",
        weight: 1,
        fillColor: color,
        fillOpacity: 0.85
      })
      .bindPopup(popupHtml)
      .bindTooltip(`${s.station_name}: ${s.temperature}°C / ${s.humidity}%`, { direction: "top" })
      .addTo(markersLayerGroup);
    });
  }
}

// 3. 渲染 Chart.js 圖表 (Gate 4)
function renderCharts(stations) {
  const displayStations = stations.slice(0, 30); // 避免圖表過密，取前 30 站
  const labels = displayStations.map(s => s.station_name);
  const temps = displayStations.map(s => s.temperature);
  const minTemps = displayStations.map(s => s.min_t);
  const maxTemps = displayStations.map(s => s.max_t);
  const hums = displayStations.map(s => s.humidity);

  // 氣溫折線圖
  const ctxTemp = document.getElementById("tempLineChart").getContext("2d");
  if (tempChart) tempChart.destroy();
  tempChart = new Chart(ctxTemp, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "即時氣溫 (°C)",
          data: temps,
          borderColor: "#2563eb",
          backgroundColor: "rgba(37, 99, 235, 0.1)",
          tension: 0.3,
          borderWidth: 2.5
        },
        {
          label: "當日最低溫 (°C)",
          data: minTemps,
          borderColor: "#38a169",
          borderDash: [4, 4],
          tension: 0.3,
          borderWidth: 1.5
        },
        {
          label: "當日最高溫 (°C)",
          data: maxTemps,
          borderColor: "#e53e3e",
          borderDash: [4, 4],
          tension: 0.3,
          borderWidth: 1.5
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "top" }
      },
      scales: {
        y: { title: { display: true, text: "氣溫 (°C)" } }
      }
    }
  });

  // 相對濕度長條圖
  const ctxHum = document.getElementById("humidityBarChart").getContext("2d");
  if (humChart) humChart.destroy();
  humChart = new Chart(ctxHum, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        {
          label: "相對濕度 (%)",
          data: hums,
          backgroundColor: "#0284c7",
          borderRadius: 4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        y: { min: 0, max: 100, title: { display: true, text: "濕度 (%)" } }
      }
    }
  });
}

// 4. 渲染數據表格
function renderTable(stations) {
  const tbody = document.getElementById("weatherTableBody");
  if (!stations.length) {
    tbody.innerHTML = '<tr><td colspan="10" class="text-center">查無相符測站資料</td></tr>';
    return;
  }

  tbody.innerHTML = stations.map(s => `
    <tr>
      <td><code>${s.station_id}</code></td>
      <td><strong>${s.station_name}</strong></td>
      <td>${s.region_name || '-'}</td>
      <td>${s.county_name || '-'}</td>
      <td>${s.town_name || '-'}</td>
      <td style="font-weight: bold; color: ${getTempColor(s.temperature)};">${s.temperature != null ? s.temperature + ' °C' : '-'}</td>
      <td>${s.humidity != null ? s.humidity + ' %' : '-'}</td>
      <td>${s.min_t != null ? s.min_t + ' °C' : '-'}</td>
      <td>${s.max_t != null ? s.max_t + ' °C' : '-'}</td>
      <td>${s.obs_time || '-'}</td>
    </tr>
  `).join("");
}

// CSV 匯出
function downloadCSV() {
  if (!currentFilteredStations.length) return;
  const headers = ["測站代碼,測站名稱,地理分區,所屬縣市,鄉鎮區,即時氣溫(°C),相對濕度(%),當日最低溫(°C),當日最高溫(°C),觀測時間"];
  const rows = currentFilteredStations.map(s => 
    `"${s.station_id}","${s.station_name}","${s.region_name || ''}","${s.county_name || ''}","${s.town_name || ''}",${s.temperature},${s.humidity},${s.min_t},${s.max_t},"${s.obs_time}"`
  );
  const csvContent = "\uFEFF" + [headers, ...rows].join("\n");
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `cwa_weather_${document.getElementById("regionSelect").value}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// 向中央氣象署即時同步資料
async function syncLiveCwaData() {
  const btn = document.getElementById("syncCwaBtn");
  if (!btn) return;
  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = "⏳ 正在連線氣象署抓取最新資料...";

  try {
    let res = await fetch("/api/sync");
    if (res.status === 404) {
      res = await fetch("/sync");
    }

    if (!res.ok) {
      let errMsg = `伺服器回應異常 (HTTP ${res.status})`;
      try {
        const errJson = await res.json();
        if (errJson.detail) errMsg += `: ${errJson.detail}`;
        else if (errJson.message) errMsg = errJson.message;
      } catch (e) {}
      alert(`⚠️ ${errMsg}，使用現有快取。`);
      return;
    }

    const data = await res.json();
    if (data.status === "success") {
      alert("✅ " + data.message);
      await fetchDashboardData();
    } else {
      alert("⚠️ " + (data.message || "同步失敗，使用現有快取。"));
    }
  } catch (err) {
    alert("❌ 無法連線至伺服器同步端點：" + err.message);
    console.error(err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalText;
  }
}

// 事件綁定
document.addEventListener("DOMContentLoaded", () => {
  // 分頁切換
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const targetId = btn.getAttribute("data-tab");
      document.getElementById(targetId).classList.add("active");

      // 若切換到地圖需強制 invalidateSize
      if (targetId === "tab-map" && mapInstance) {
        setTimeout(() => mapInstance.invalidateSize(), 150);
      }
    });
  });

  // 篩選與搜尋
  document.getElementById("regionSelect").addEventListener("change", applyFilterAndRender);
  document.getElementById("stationSearch").addEventListener("input", applyFilterAndRender);
  
  const syncBtn = document.getElementById("syncCwaBtn");
  if (syncBtn) {
    syncBtn.addEventListener("click", syncLiveCwaData);
  }

  document.getElementById("downloadCsvBtn").addEventListener("click", downloadCSV);

  // 地圖模式切換
  document.querySelectorAll('input[name="mapMode"]').forEach(radio => {
    radio.addEventListener("change", renderMap);
  });

  // 初始讀取
  fetchDashboardData();
});

