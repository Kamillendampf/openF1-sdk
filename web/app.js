const canvas = document.getElementById("trackCanvas");
const ctx = canvas.getContext("2d");
const loadBtn = document.getElementById("loadBtn");
const loadBtnLabel = document.getElementById("loadBtnLabel");
const meta = document.getElementById("meta");
const errorBox = document.getElementById("errorBox");
const sessionPill = document.getElementById("sessionPill");
const circuitValue = document.getElementById("circuitValue");
const driverCount = document.getElementById("driverCount");
const pointCount = document.getElementById("pointCount");
const lapValue = document.getElementById("lapValue");
const driverGrid = document.getElementById("driverGrid");
const trackOverlay = document.getElementById("trackOverlay");
const positionList = document.getElementById("positionList");
const modeSelect = document.getElementById("modeSelect");
const yearControl = document.getElementById("yearControl");
const yearSelect = document.getElementById("yearSelect");
const sessionControl = document.getElementById("sessionControl");
const sessionSelect = document.getElementById("sessionSelect");
const replayControl = document.getElementById("replayControl");
const replayBackBtn = document.getElementById("replayBackBtn");
const replayPlayPauseBtn = document.getElementById("replayPlayPauseBtn");
const replayForwardBtn = document.getElementById("replayForwardBtn");
const replaySpeedSelect = document.getElementById("replaySpeedSelect");
const replayTimeline = document.getElementById("replayTimeline");
const replayTimelineValue = document.getElementById("replayTimelineValue");

const LIVE_INTERVAL_MS = 1000;
const HISTORY_FALLBACK_DELAY_MS = 80;
const LIVE_MARKER_ANIMATION_FACTOR = 0.85;
const HISTORY_MARKER_ANIMATION_FACTOR = 0.85;
let liveTimerId = null;
let historyPlaybackTimeoutId = null;
let historyEvents = [];
let historyEventIndex = 0;
let historyLapCurrent = 1;
let historyLapMax = null;
let historyReplaySessionKey = null;
let historyReplayLapNumbers = [];
let historyReplayLapIndex = 0;
let historyReplayLoading = false;
let historyLapCache = new Map();
let historyPlaybackSpeed = 1;
let historyPlaybackPaused = false;
let historyLastDelayMs = HISTORY_FALLBACK_DELAY_MS;
let historyLapCompleteCallback = null;
let currentPoints = [];
let currentDrivers = [];
let liveEnabled = false;
let currentMode = "live";
let trackMarkersByDriver = new Map();

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function driverDisplayName(driver) {
  if (driver.full_name) return driver.full_name;
  const first = driver.first_name || "";
  const last = driver.last_name || "";
  const full = `${first} ${last}`.trim();
  if (full) return full;
  return driver.name_acronym || "Unknown Driver";
}

function formatIsoTime(isoString) {
  if (!isoString || typeof isoString !== "string") return "";
  const parsed = new Date(isoString);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleTimeString("de-DE");
}

function formatIsoDateTime(isoString) {
  if (!isoString || typeof isoString !== "string") return "";
  const parsed = new Date(isoString);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleString("de-DE");
}

function resizeCanvas() {
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.floor(rect.width * ratio);
  canvas.height = Math.floor(rect.height * ratio);
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  if (currentPoints.length >= 2) {
    drawTrack(currentPoints);
    renderTrackDrivers(currentPoints, currentDrivers, { immediate: true });
  } else {
    ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);
    clearTrackMarkers();
  }
}

function bounds(points) {
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };
}

function createProjector(points) {
  const b = bounds(points);
  const pad = 20;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  const spanX = Math.max(1, b.maxX - b.minX);
  const spanY = Math.max(1, b.maxY - b.minY);
  const fitScale = Math.min((w - pad * 2) / spanX, (h - pad * 2) / spanY);
  const scale = fitScale * 0.95;
  const offsetX = (w - spanX * scale) / 2;
  const offsetY = (h - spanY * scale) / 2;

  return (p) => {
    const x = (p.x - b.minX) * scale + offsetX;
    const y = h - ((p.y - b.minY) * scale + offsetY);
    return { x, y };
  };
}

function drawTrack(points) {
  ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);
  if (points.length < 2) return;

  const project = createProjector(points);
  const pp = points.map(project);

  ctx.lineJoin = "round";
  ctx.lineCap = "round";

  ctx.beginPath();
  ctx.moveTo(pp[0].x, pp[0].y);
  for (let i = 1; i < pp.length; i += 1) {
    ctx.lineTo(pp[i].x, pp[i].y);
  }
  ctx.strokeStyle = "rgba(255, 36, 56, 0.18)";
  ctx.lineWidth = 20;
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(pp[0].x, pp[0].y);
  for (let i = 1; i < pp.length; i += 1) {
    ctx.lineTo(pp[i].x, pp[i].y);
  }
  ctx.strokeStyle = "#3f4554";
  ctx.lineWidth = 12;
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(pp[0].x, pp[0].y);
  for (let i = 1; i < pp.length; i += 1) {
    ctx.lineTo(pp[i].x, pp[i].y);
  }
  ctx.strokeStyle = "rgba(171, 181, 199, 0.55)";
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

function setTrack(points) {
  if (!Array.isArray(points) || points.length < 2) {
    currentPoints = [];
    ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);
    clearTrackMarkers();
    pointCount.textContent = "0";
    return;
  }
  currentPoints = points;
  pointCount.textContent = String(points.length);
  drawTrack(points);
  renderTrackDrivers(points, currentDrivers, { immediate: true });
}

function clearTrackMarkers() {
  for (const marker of trackMarkersByDriver.values()) {
    marker.remove();
  }
  trackMarkersByDriver = new Map();
}

function markerColor(driver) {
  return typeof driver.team_colour === "string" && driver.team_colour
    ? `#${driver.team_colour.replace("#", "")}`
    : "#dbe4fb";
}

function markerKey(driver, index) {
  if (driver && typeof driver.driver_number === "number") {
    return `num-${driver.driver_number}`;
  }
  const fallback = String(driver?.name_acronym || driverDisplayName(driver) || index || "unknown")
    .trim()
    .toUpperCase();
  return `fallback-${fallback}`;
}

function markerSignature(driver) {
  return [
    driver?.driver_number ?? "",
    driver?.name_acronym ?? "",
    driver?.full_name ?? "",
    driver?.first_name ?? "",
    driver?.last_name ?? "",
    driver?.team_colour ?? "",
    driver?.headshot_url ?? "",
  ].join("|");
}

function setMarkerFallback(marker, fallback, badgeText, color) {
  marker.innerHTML = "";
  marker.classList.add("no-image");
  marker.appendChild(document.createTextNode(fallback));
  const badge = document.createElement("span");
  badge.className = "track-driver-badge";
  badge.style.borderColor = color;
  badge.textContent = badgeText;
  marker.appendChild(badge);
}

function updateMarkerIdentity(marker, driver) {
  const signature = markerSignature(driver);
  if (marker.dataset.signature === signature) {
    return;
  }

  marker.dataset.signature = signature;
  marker.innerHTML = "";
  marker.classList.remove("no-image");

  const color = markerColor(driver);
  const fallback = (driver.name_acronym || String(driver.driver_number || "?")).slice(0, 3).toUpperCase();
  const imageUrl = typeof driver.headshot_url === "string" ? driver.headshot_url : "";
  const badgeText = String(driver.driver_number ?? "");
  marker.style.borderColor = color;
  marker.dataset.imageUrl = imageUrl;

  if (imageUrl) {
    const img = document.createElement("img");
    img.src = imageUrl;
    img.alt = driverDisplayName(driver);
    img.loading = "lazy";
    img.referrerPolicy = "no-referrer";
    img.addEventListener("error", () => {
      if (marker.dataset.imageUrl !== imageUrl) {
        return;
      }
      setMarkerFallback(marker, fallback, badgeText, color);
    });
    marker.appendChild(img);
  } else {
    marker.classList.add("no-image");
    marker.appendChild(document.createTextNode(fallback));
  }

  const badge = document.createElement("span");
  badge.className = "track-driver-badge";
  badge.style.borderColor = color;
  badge.textContent = badgeText;
  marker.appendChild(badge);
}

function markerTransitionDurationMs(immediate) {
  if (immediate) {
    return 0;
  }
  if (currentMode === "live") {
    return Math.max(80, Math.round(LIVE_INTERVAL_MS * LIVE_MARKER_ANIMATION_FACTOR));
  }
  const historyDuration = Math.round(historyLastDelayMs * HISTORY_MARKER_ANIMATION_FACTOR);
  return Math.max(25, Math.min(260, historyDuration));
}

function renderTrackDrivers(points, drivers, options = {}) {
  const immediate = Boolean(options && options.immediate);
  if (points.length < 2 || !drivers.length) {
    clearTrackMarkers();
    return;
  }

  const project = createProjector(points);
  const activeKeys = new Set();
  const transitionMs = markerTransitionDurationMs(immediate);

  for (let idx = 0; idx < drivers.length; idx += 1) {
    const driver = drivers[idx];
    const tp = driver && typeof driver === "object" ? driver.track_point : null;
    if (!tp || typeof tp.x !== "number" || typeof tp.y !== "number") {
      continue;
    }
    const key = markerKey(driver, idx);
    const projected = project(tp);
    activeKeys.add(key);

    let marker = trackMarkersByDriver.get(key);
    if (!marker) {
      marker = document.createElement("div");
      marker.className = "track-driver";
      marker.style.left = `${projected.x}px`;
      marker.style.top = `${projected.y}px`;
      marker.style.transition = "none";
      trackOverlay.appendChild(marker);
      trackMarkersByDriver.set(key, marker);
      window.requestAnimationFrame(() => {
        if (!marker || !marker.isConnected) {
          return;
        }
        marker.style.transition = transitionMs > 0
          ? `left ${transitionMs}ms linear, top ${transitionMs}ms linear`
          : "none";
      });
    } else {
      marker.style.transition = transitionMs > 0
        ? `left ${transitionMs}ms linear, top ${transitionMs}ms linear`
        : "none";
      marker.style.left = `${projected.x}px`;
      marker.style.top = `${projected.y}px`;
    }
    updateMarkerIdentity(marker, driver);
  }

  for (const [key, marker] of trackMarkersByDriver.entries()) {
    if (!activeKeys.has(key)) {
      marker.remove();
      trackMarkersByDriver.delete(key);
    }
  }
}
function sortedByPosition(drivers) {
  return [...drivers].sort((a, b) => {
    const pa = typeof a.current_position === "number" ? a.current_position : 999;
    const pb = typeof b.current_position === "number" ? b.current_position : 999;
    if (pa !== pb) return pa - pb;
    const da = typeof a.driver_number === "number" ? a.driver_number : 999;
    const db = typeof b.driver_number === "number" ? b.driver_number : 999;
    return da - db;
  });
}

function renderPositions(drivers) {
  if (!drivers.length) {
    positionList.innerHTML = '<div class="empty-note">Keine Positionsdaten vorhanden.</div>';
    return;
  }

  const sorted = sortedByPosition(drivers);
  positionList.innerHTML = sorted
    .map((driver, idx) => {
      const position = typeof driver.current_position === "number" ? driver.current_position : idx + 1;
      const acronym = driver.name_acronym || "";
      const name = driverDisplayName(driver);
      const team = driver.team_name || "Unknown Team";
      const lap = typeof driver.current_lap === "number" ? `Lap ${driver.current_lap}` : "-";
      return `
        <article class="position-row">
          <div class="position-rank">P${escapeHtml(position)}</div>
          <div class="position-main">
            <div class="position-name">${escapeHtml(acronym || name)}</div>
            <div class="position-meta">${escapeHtml(team)}</div>
          </div>
          <div class="position-lap">${escapeHtml(lap)}</div>
        </article>
      `;
    })
    .join("");
}

function renderDrivers(drivers) {
  if (!drivers.length) {
    driverGrid.innerHTML = '<div class="empty-note">Keine Fahrerdaten vorhanden.</div>';
    return;
  }

  driverGrid.innerHTML = sortedByPosition(drivers)
    .map((driver) => {
      const number = driver.driver_number ?? "-";
      const acronym = driver.name_acronym || "";
      const name = driverDisplayName(driver);
      const team = driver.team_name || "Unknown Team";
      const imageUrl = typeof driver.headshot_url === "string" ? driver.headshot_url : "";
      const fallback = (acronym || String(number)).slice(0, 3).toUpperCase();
      const positionText = typeof driver.current_position === "number" ? `P${driver.current_position}` : "-";
      return `
        <article class="driver-card">
          <div class="driver-main">
            <div class="driver-face${imageUrl ? "" : " is-empty"}">
              ${imageUrl
                ? `<img src="${escapeHtml(imageUrl)}" alt="${escapeHtml(name)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove();this.parentElement.classList.add('is-empty');this.parentElement.textContent='${escapeHtml(fallback)}';" />`
                : `${escapeHtml(fallback)}`}
            </div>
            <div class="driver-ident">
              <div class="driver-top">
                <div class="driver-num">#${escapeHtml(number)}</div>
                <div class="driver-acr">${escapeHtml(positionText)}</div>
              </div>
              <div class="driver-name">${escapeHtml(name)}</div>
            </div>
          </div>
          <div class="driver-team">${escapeHtml(team)}</div>
        </article>
      `;
    })
    .join("");
}

function setLapFromPayload(lap) {
  if (!lap || typeof lap !== "object") {
    lapValue.textContent = "-/-";
    return;
  }
  if (typeof lap.display === "string" && lap.display) {
    lapValue.textContent = lap.display;
    return;
  }
  const current = typeof lap.current === "number" ? lap.current : "-";
  const max = typeof lap.max === "number" ? lap.max : "-";
  lapValue.textContent = `${current}/${max}`;
}

function setSessionHeadline(circuitName, sessionName) {
  const circuit = circuitName || "Unknown Circuit";
  circuitValue.textContent = circuit;
  sessionPill.textContent = sessionName ? `${circuit} - ${sessionName}` : circuit;
}

function updateReplayTimelineUi() {
  const firstLap = historyReplayLapNumbers.length ? historyReplayLapNumbers[0] : 1;
  const lastLap = historyReplayLapNumbers.length ? historyReplayLapNumbers[historyReplayLapNumbers.length - 1] : firstLap;
  replayTimeline.min = String(firstLap);
  replayTimeline.max = String(lastLap);
  replayTimeline.value = String(historyLapCurrent || firstLap);
  replayTimelineValue.textContent = `Lap ${historyLapCurrent || firstLap}/${lastLap}`;
}

function updateReplayControlsUi() {
  const isHistory = currentMode === "history";
  replayControl.classList.toggle("hidden", !isHistory);
  const hasSession = Boolean(historyReplaySessionKey);
  const hasPrev = hasSession && historyReplayLapIndex > 0;
  const hasNext = hasSession && historyReplayLapIndex < historyReplayLapNumbers.length - 1;
  replayBackBtn.disabled = !hasPrev || historyReplayLoading;
  replayForwardBtn.disabled = !hasNext || historyReplayLoading;
  replayTimeline.disabled = !hasSession || historyReplayLoading;
  replaySpeedSelect.disabled = !hasSession;
  replayPlayPauseBtn.disabled = !hasSession || historyReplayLoading;
  replayPlayPauseBtn.textContent = historyPlaybackPaused ? "Play" : "Pause";
  updateReplayTimelineUi();
}

function applyHistoryEvent(event) {
  const driver = currentDrivers.find((row) => row.driver_number === event.driver_number);
  if (!driver) return;

  driver.track_point = {
    x: event.x,
    y: event.y,
    z: event.z,
    date: event.date,
  };
  if (typeof event.lap_number === "number" && event.lap_number > 0) {
    driver.current_lap = event.lap_number;
    if (event.lap_number > historyLapCurrent) {
      historyLapCurrent = event.lap_number;
    }
  }
}

function playbackDelayMs(currentEvent, nextEvent) {
  if (!currentEvent || !nextEvent) return HISTORY_FALLBACK_DELAY_MS;
  const currentMs = Date.parse(currentEvent.date);
  const nextMs = Date.parse(nextEvent.date);
  if (!Number.isFinite(currentMs) || !Number.isFinite(nextMs)) {
    return HISTORY_FALLBACK_DELAY_MS;
  }
  const delta = Math.max(1, nextMs - currentMs);
  const scaled = delta / Math.max(1, historyPlaybackSpeed);
  return Math.max(10, Math.min(1200, Math.round(scaled)));
}

function applyBootstrapPayload(data) {
  const points = Array.isArray(data.points) ? data.points : [];
  const drivers = Array.isArray(data.drivers) ? data.drivers : [];
  const circuit = typeof data.circuit_name === "string" ? data.circuit_name : "Unknown Circuit";
  const sessionName = typeof data.session_name === "string" ? data.session_name : "";

  currentDrivers = drivers;
  driverCount.textContent = String(drivers.length);
  setSessionHeadline(circuit, sessionName);
  setLapFromPayload(data.lap);
  renderDrivers(drivers);
  renderPositions(drivers);
  setTrack(points);
}

function applyLivePayload(data) {
  const livePoints = Array.isArray(data.track) ? data.track : [];
  const liveDrivers = Array.isArray(data.drivers) ? data.drivers : [];
  const circuit = typeof data.circuit_name === "string" ? data.circuit_name : circuitValue.textContent;
  const sessionName = typeof data.session_name === "string" ? data.session_name : "";

  if (livePoints.length >= 2) {
    setTrack(livePoints);
  }
  if (liveDrivers.length) {
    currentDrivers = liveDrivers;
  }

  driverCount.textContent = String(currentDrivers.length);
  setSessionHeadline(circuit, sessionName);
  setLapFromPayload(data.lap);
  renderDrivers(currentDrivers);
  renderPositions(currentDrivers);
  renderTrackDrivers(currentPoints, currentDrivers);

  const ts = formatIsoTime(data.position_timestamp || data.generated_at);
  meta.textContent = ts ? `Live aktiv - Letztes Update ${ts}` : "Live aktiv";
  errorBox.textContent = "";
}

function stopHistoryPlayback() {
  if (historyPlaybackTimeoutId !== null) {
    clearTimeout(historyPlaybackTimeoutId);
    historyPlaybackTimeoutId = null;
  }
  historyLapCompleteCallback = null;
  historyEvents = [];
  historyEventIndex = 0;
}

function resetHistoryReplayState() {
  stopHistoryPlayback();
  historyLapCurrent = 1;
  historyLapMax = null;
  historyReplaySessionKey = null;
  historyReplayLapNumbers = [];
  historyReplayLapIndex = 0;
  historyReplayLoading = false;
  historyLapCache = new Map();
  historyPlaybackPaused = false;
  historyLastDelayMs = HISTORY_FALLBACK_DELAY_MS;
  updateReplayControlsUi();
}

function runHistoryPlayback() {
  if (historyPlaybackPaused) {
    return;
  }
  if (historyEventIndex >= historyEvents.length) {
    const callback = historyLapCompleteCallback;
    stopHistoryPlayback();
    if (typeof callback === "function") {
      callback();
    } else {
      meta.textContent = "Historischer Replay abgeschlossen.";
    }
    return;
  }

  const currentEvent = historyEvents[historyEventIndex];
  applyHistoryEvent(currentEvent);
  historyEventIndex += 1;

  renderTrackDrivers(currentPoints, currentDrivers);
  renderDrivers(currentDrivers);
  renderPositions(currentDrivers);

  const maxLap = typeof historyLapMax === "number" ? historyLapMax : null;
  setLapFromPayload({
    current: historyLapCurrent,
    max: maxLap,
    display: maxLap ? `${historyLapCurrent}/${maxLap}` : `${historyLapCurrent}/-`,
  });
  updateReplayTimelineUi();

  const progress = Math.min(100, Math.round((historyEventIndex / historyEvents.length) * 100));
  const ts = formatIsoTime(currentEvent.date);
  meta.textContent = ts
    ? `Historischer Replay: Lap ${historyLapCurrent} - ${progress}% - ${ts} (${historyPlaybackSpeed}x)`
    : `Historischer Replay: Lap ${historyLapCurrent} - ${progress}% (${historyPlaybackSpeed}x)`;

  const nextEvent = historyEventIndex < historyEvents.length ? historyEvents[historyEventIndex] : null;
  const delay = playbackDelayMs(currentEvent, nextEvent);
  historyLastDelayMs = delay;
  historyPlaybackTimeoutId = window.setTimeout(runHistoryPlayback, delay);
}

function startHistoryPlayback(playback, onComplete) {
  stopHistoryPlayback();
  const events = playback && Array.isArray(playback.events) ? playback.events : [];
  if (!events.length) {
    meta.textContent = "Historisch geladen, aber keine Bewegungsdaten vorhanden.";
    return;
  }

  historyEvents = events;
  historyEventIndex = 0;
  historyLapCompleteCallback = onComplete;
  updateReplayControlsUi();
  if (!historyPlaybackPaused) {
    runHistoryPlayback();
  }
}

function pauseHistoryPlayback() {
  historyPlaybackPaused = true;
  if (historyPlaybackTimeoutId !== null) {
    clearTimeout(historyPlaybackTimeoutId);
    historyPlaybackTimeoutId = null;
  }
  updateReplayControlsUi();
}

function resumeHistoryPlayback() {
  if (!historyPlaybackPaused) {
    return;
  }
  historyPlaybackPaused = false;
  updateReplayControlsUi();
  if (currentMode === "history" && historyReplaySessionKey) {
    if (historyEvents.length > 0 && historyEventIndex < historyEvents.length) {
      runHistoryPlayback();
      return;
    }
    if (!historyReplayLoading) {
      void loadAndPlayHistoryLap();
    }
  }
}

function toggleHistoryPlayback() {
  if (historyPlaybackPaused) {
    resumeHistoryPlayback();
  } else {
    pauseHistoryPlayback();
  }
}

async function loadAndPlayHistoryLap(targetLapNumber = null) {
  if (currentMode !== "history" || !historyReplaySessionKey) {
    return;
  }
  if (historyReplayLoading) {
    return;
  }
  if (targetLapNumber !== null) {
    const wantedIndex = historyReplayLapNumbers.indexOf(targetLapNumber);
    if (wantedIndex === -1) {
      return;
    }
    historyReplayLapIndex = wantedIndex;
  }
  if (historyReplayLapIndex < 0 || historyReplayLapIndex >= historyReplayLapNumbers.length) {
    meta.textContent = "Historischer Replay abgeschlossen.";
    return;
  }

  const lapNumber = historyReplayLapNumbers[historyReplayLapIndex];
  historyReplayLoading = true;
  updateReplayControlsUi();
  try {
    let data = historyLapCache.get(lapNumber);
    if (!data) {
      data = await fetchJson(
        `/api/history/replay/lap?session_key=${encodeURIComponent(historyReplaySessionKey)}&lap_number=${encodeURIComponent(lapNumber)}&sample_step=8`
      );
      historyLapCache.set(lapNumber, data);
    }
    historyReplayLoading = false;
    historyLapCurrent = lapNumber;
    setLapFromPayload({
      current: lapNumber,
      max: historyLapMax,
      display: historyLapMax ? `${lapNumber}/${historyLapMax}` : `${lapNumber}/-`,
    });
    replayTimeline.value = String(lapNumber);
    updateReplayControlsUi();

    startHistoryPlayback(data.playback, async () => {
      historyReplayLapIndex += 1;
      updateReplayControlsUi();
      await loadAndPlayHistoryLap();
    });
  } catch (err) {
    historyReplayLoading = false;
    updateReplayControlsUi();
    meta.textContent = "Fehler beim historischen Replay.";
    errorBox.textContent = String(err);
  }
}

async function seekToLap(lapNumber) {
  if (!historyReplaySessionKey || !Number.isInteger(lapNumber)) {
    return;
  }
  const wasPaused = historyPlaybackPaused;
  stopHistoryPlayback();
  historyPlaybackPaused = wasPaused;
  await loadAndPlayHistoryLap(lapNumber);
}

async function stepLap(delta) {
  if (!historyReplaySessionKey) {
    return;
  }
  const target = historyLapCurrent + delta;
  if (!historyReplayLapNumbers.includes(target)) {
    return;
  }
  await seekToLap(target);
}

function applyHistoryReplayInit(data) {
  const points = Array.isArray(data.track) ? data.track : [];
  const drivers = Array.isArray(data.drivers) ? data.drivers : [];
  const circuit = typeof data.circuit_name === "string" ? data.circuit_name : "Unknown Circuit";
  const sessionName = typeof data.session_name === "string" ? data.session_name : "Session";
  const startDate = formatIsoDateTime(data.date_start);

  currentDrivers = drivers.map((driver) => ({
    ...driver,
    track_point: null,
    current_lap: 1,
    lap_date: null,
  }));
  driverCount.textContent = String(currentDrivers.length);
  setSessionHeadline(circuit, sessionName);
  historyLapCurrent = 1;
  historyLapMax = data && data.lap && typeof data.lap.max === "number" ? data.lap.max : null;
  historyReplaySessionKey = data && typeof data.session_key === "number" ? data.session_key : null;
  historyReplayLapNumbers = Array.isArray(data?.replay?.lap_numbers)
    ? data.replay.lap_numbers.filter((lap) => Number.isInteger(lap) && lap > 0)
    : [];
  historyReplayLapIndex = 0;
  if (!historyReplayLapNumbers.length) {
    historyReplayLapNumbers = [1];
  }
  historyPlaybackPaused = false;
  setLapFromPayload({
    current: 1,
    max: historyLapMax,
    display: historyLapMax ? `1/${historyLapMax}` : "1/-",
  });
  renderDrivers(currentDrivers);
  renderPositions(currentDrivers);
  setTrack(points);
  meta.textContent = startDate ? `Historisch - ${startDate}` : "Historischer Replay initialisiert";
  errorBox.textContent = "";
  updateReplayControlsUi();
}

async function fetchJson(url) {
  const res = await fetch(url);
  const raw = await res.text();
  let data = {};
  try {
    data = JSON.parse(raw);
  } catch {
    throw new Error("Antwort ist kein gueltiges JSON.");
  }
  if (!res.ok) {
    throw new Error(data.detail || data.error || `HTTP ${res.status}`);
  }
  return data;
}

function stopLivePolling() {
  if (liveTimerId !== null) {
    clearInterval(liveTimerId);
    liveTimerId = null;
  }
  liveEnabled = false;
}

function stopAllStreaming() {
  stopLivePolling();
  stopHistoryPlayback();
  historyReplayLoading = false;
}

async function fetchLiveSnapshot() {
  if (!liveEnabled || currentMode !== "live") return;

  try {
    const data = await fetchJson("/api/live");
    applyLivePayload(data);
  } catch (err) {
    if (String(err).includes("HTTP 503")) {
      stopLivePolling();
      meta.textContent = "Track geladen, Live-Stream nicht verfuegbar (OAuth/MQTT nicht aktiv).";
      return;
    }
    if (liveEnabled) {
      errorBox.textContent = `Live-Update Fehler: ${String(err)}`;
    }
  }
}

function startLivePolling() {
  stopLivePolling();
  liveEnabled = true;
  liveTimerId = window.setInterval(fetchLiveSnapshot, LIVE_INTERVAL_MS);
}
function buildYearOptions() {
  const currentYear = new Date().getFullYear();
  yearSelect.innerHTML = "";
  for (let year = currentYear; year >= currentYear - 10; year -= 1) {
    const option = document.createElement("option");
    option.value = String(year);
    option.textContent = String(year);
    yearSelect.appendChild(option);
  }
  yearSelect.value = String(currentYear);
}

function populateSessionSelect(sessions) {
  sessionSelect.innerHTML = "";
  if (!Array.isArray(sessions) || !sessions.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Keine Sessions gefunden";
    sessionSelect.appendChild(option);
    return;
  }

  for (const session of sessions) {
    const key = session.session_key;
    const date = formatIsoDateTime(session.date_start);
    const label = `${date || "-"} | ${session.circuit_name || "-"} | ${session.session_name || "-"}`;
    const option = document.createElement("option");
    option.value = String(key);
    option.textContent = label;
    sessionSelect.appendChild(option);
  }
}

async function loadHistorySessions() {
  const year = yearSelect.value;
  meta.textContent = "Lade historische Sessions...";
  const data = await fetchJson(`/api/history/sessions?year=${encodeURIComponent(year)}&limit=120`);
  const sessions = Array.isArray(data.sessions) ? data.sessions : [];
  populateSessionSelect(sessions);
  meta.textContent = sessions.length
    ? `Historische Sessions geladen (${sessions.length})`
    : "Keine historischen Sessions gefunden.";
  return sessions;
}

async function loadLiveMode() {
  errorBox.textContent = "";
  meta.textContent = "Lade Live-Basisdaten...";
  stopAllStreaming();
  resetHistoryReplayState();
  const data = await fetchJson("/api/run");
  applyBootstrapPayload(data);
  meta.textContent = "Track geladen. Starte Live-Updates...";
  startLivePolling();
  await fetchLiveSnapshot();
}

async function loadHistoricalMode() {
  errorBox.textContent = "";
  stopAllStreaming();
  resetHistoryReplayState();
  if (!sessionSelect.value) {
    const sessions = await loadHistorySessions();
    if (!sessions.length || !sessionSelect.value) {
      throw new Error("Keine historische Session auswaehlbar.");
    }
  }

  meta.textContent = "Lade historische Replay-Metadaten...";
  const sessionKey = sessionSelect.value;
  const data = await fetchJson(`/api/history/replay/init?session_key=${encodeURIComponent(sessionKey)}`);
  applyHistoryReplayInit(data);
  await loadAndPlayHistoryLap();
}

function updateModeUi() {
  const isHistory = currentMode === "history";
  yearControl.classList.toggle("hidden", !isHistory);
  sessionControl.classList.toggle("hidden", !isHistory);
  replayControl.classList.toggle("hidden", !isHistory);
  loadBtnLabel.textContent = isHistory ? "Historie Laden" : "Live Laden";
  updateReplayControlsUi();
}

async function loadCurrentMode() {
  if (currentMode === "history") {
    await loadHistoricalMode();
  } else {
    await loadLiveMode();
  }
}

modeSelect.addEventListener("change", async () => {
  currentMode = modeSelect.value === "history" ? "history" : "live";
  updateModeUi();
  try {
    if (currentMode === "history") {
      await loadHistorySessions();
      await loadHistoricalMode();
    } else {
      await loadLiveMode();
    }
  } catch (err) {
    meta.textContent = "Fehler beim Laden.";
    errorBox.textContent = String(err);
  }
});

yearSelect.addEventListener("change", async () => {
  if (currentMode !== "history") return;
  try {
    await loadHistorySessions();
    await loadHistoricalMode();
  } catch (err) {
    meta.textContent = "Fehler beim Laden.";
    errorBox.textContent = String(err);
  }
});

sessionSelect.addEventListener("change", async () => {
  if (currentMode !== "history" || !sessionSelect.value) return;
  try {
    await loadHistoricalMode();
  } catch (err) {
    meta.textContent = "Fehler beim Laden.";
    errorBox.textContent = String(err);
  }
});

loadBtn.addEventListener("click", async () => {
  try {
    await loadCurrentMode();
  } catch (err) {
    meta.textContent = "Fehler beim Laden.";
    errorBox.textContent = String(err);
  }
});

replaySpeedSelect.addEventListener("change", () => {
  const speed = Number.parseInt(replaySpeedSelect.value, 10);
  historyPlaybackSpeed = Number.isFinite(speed) && speed > 0 ? speed : 1;
  updateReplayControlsUi();
});

replayPlayPauseBtn.addEventListener("click", () => {
  toggleHistoryPlayback();
});

replayBackBtn.addEventListener("click", async () => {
  await stepLap(-1);
});

replayForwardBtn.addEventListener("click", async () => {
  await stepLap(1);
});

replayTimeline.addEventListener("input", () => {
  const value = Number.parseInt(replayTimeline.value, 10);
  const max = historyReplayLapNumbers.length ? historyReplayLapNumbers[historyReplayLapNumbers.length - 1] : value;
  replayTimelineValue.textContent = `Lap ${value}/${max}`;
});

replayTimeline.addEventListener("change", async () => {
  const value = Number.parseInt(replayTimeline.value, 10);
  if (!Number.isInteger(value)) {
    return;
  }
  await seekToLap(value);
});

window.addEventListener("resize", resizeCanvas);

replaySpeedSelect.value = String(historyPlaybackSpeed);
buildYearOptions();
updateModeUi();
resizeCanvas();
loadLiveMode().catch((err) => {
  meta.textContent = "Fehler beim Laden.";
  errorBox.textContent = String(err);
});
