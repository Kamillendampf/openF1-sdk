import {
  AfterViewInit,
  Component,
  DestroyRef,
  ElementRef,
  ViewChild,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { firstValueFrom } from 'rxjs';

import { OpenF1ApiService } from '../../core/openf1-api.service';
import {
  DriverPayload,
  LivePayload,
  RunPayload,
  TeamRadioEventPayload,
  TeamRadioInsightsPayload,
  TrackPoint,
  WeatherInsightsPayload,
} from '../../core/openf1.models';

const LIVE_POLL_INTERVAL_MS = 1000;
const WEATHER_POLL_INTERVAL_MS = 15000;
const TEAM_RADIO_POLL_INTERVAL_MS = 10000;
const TEAM_RADIO_LIMIT = 25;
const TEAM_RADIO_ACTIVE_WINDOW_MS = 18000;
const TEAM_RADIO_ACTIVITY_TICK_MS = 1000;
const TEAM_RADIO_SEEN_LIMIT = 240;

@Component({
  selector: 'app-live-view',
  imports: [CommonModule],
  templateUrl: './live-view.html',
  styleUrl: './live-view.scss',
})
export class LiveViewComponent implements AfterViewInit {
  private readonly api = inject(OpenF1ApiService);
  private readonly destroyRef = inject(DestroyRef);
  private pollHandles: number[] = [];
  private resizeHandler: (() => void) | null = null;
  private canvasRetryHandle: number | null = null;
  private fullscreenChangeHandler: (() => void) | null = null;
  private audioElement: HTMLAudioElement | null = null;
  private queuedTeamRadioEvents: TeamRadioEventPayload[] = [];
  private seenTeamRadioEventKeys = new Set<string>();
  private activeRadioUntilByDriver = new Map<number, number>();
  private latestTeamRadioByDriver = new Map<number, TeamRadioEventPayload>();
  private isTeamRadioPlaybackRunning = false;
  private teamRadioSessionKey: number | string | null = null;

  @ViewChild('trackShell') private trackShell?: ElementRef<HTMLElement>;
  @ViewChild('trackCanvas') private trackCanvas?: ElementRef<HTMLCanvasElement>;

  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly liveUnavailable = signal(false);

  readonly bootstrap = signal<RunPayload | null>(null);
  readonly live = signal<LivePayload | null>(null);
  readonly weather = signal<WeatherInsightsPayload | null>(null);
  readonly teamRadio = signal<TeamRadioInsightsPayload | null>(null);

  readonly liveLatencyMs = signal<number | null>(null);
  readonly isTrackFullscreen = signal(false);
  readonly globalTeamRadioEnabled = signal(true);
  readonly soloDriverNumber = signal<number | null>(null);
  readonly activeRadioDriverNumbers = signal<number[]>([]);
  readonly nowTalkingDriverNumber = signal<number | null>(null);
  readonly heartbeatNowMs = signal(Date.now());

  readonly currentTrack = computed<TrackPoint[]>(() => {
    const liveTrack = this.live()?.track;
    if (Array.isArray(liveTrack) && liveTrack.length >= 2) {
      return liveTrack;
    }
    const bootstrapTrack = this.bootstrap()?.points;
    return Array.isArray(bootstrapTrack) ? bootstrapTrack : [];
  });

  readonly currentDrivers = computed<DriverPayload[]>(() => {
    const liveDrivers = this.live()?.drivers;
    if (Array.isArray(liveDrivers) && liveDrivers.length) {
      return this.normalizeDrivers(liveDrivers);
    }
    if (this.liveUnavailable()) {
      const bootstrapDrivers = this.bootstrap()?.drivers;
      return Array.isArray(bootstrapDrivers) ? this.normalizeDrivers(bootstrapDrivers) : [];
    }
    return [];
  });

  readonly currentLapDisplay = computed<string>(() => {
    const lap = this.live()?.lap?.display ?? this.bootstrap()?.lap?.display;
    return lap ?? '-';
  });

  readonly sessionTitle = computed<string>(() => {
    const source = this.live() ?? this.bootstrap();
    if (!source) {
      return 'Keine Session geladen';
    }
    return `${source.circuit_name} - ${source.session_name}`;
  });

  readonly weatherIcon = computed<string>(() => {
    const icon = this.weather()?.latest?.icon;
    if (icon === 'rain') return 'RAIN';
    if (icon === 'cloud') return 'CLOUD';
    if (icon === 'sun-high') return 'HEAT';
    return 'SUN';
  });

  readonly driversSorted = computed<DriverPayload[]>(() => {
    return [...this.currentDrivers()].sort((a, b) => {
      const posA = typeof a.current_position === 'number' ? a.current_position : 999;
      const posB = typeof b.current_position === 'number' ? b.current_position : 999;
      return posA - posB;
    });
  });

  readonly driverLayoutCount = computed<number>(() => {
    return Math.max(1, this.driversSorted().length);
  });

  readonly nowTalkingLabel = computed<string | null>(() => {
    const solo = this.soloDriverNumber();
    if (solo !== null) {
      return `Solo #${solo}`;
    }

    const talkingNumber = this.nowTalkingDriverNumber();
    if (talkingNumber === null) {
      return null;
    }
    const driver = this.currentDrivers().find((item) => item.driver_number === talkingNumber);
    const label = driver?.name_acronym ?? `#${talkingNumber}`;
    return `Funk aktiv ${label}`;
  });

  readonly elapsedTimeLabel = computed<string>(() => {
    const startValue = this.live()?.session_started_at;
    if (!startValue) {
      return '--:--:--';
    }
    const startedAt = Date.parse(startValue);
    if (!Number.isFinite(startedAt)) {
      return '--:--:--';
    }

    const generatedAt = this.live()?.generated_at;
    const generatedAtMs = generatedAt ? Date.parse(generatedAt) : Number.NaN;
    const nowMs = Number.isFinite(generatedAtMs) ? generatedAtMs : this.heartbeatNowMs();
    const deltaMs = Math.max(0, nowMs - startedAt);
    return this.formatDuration(deltaMs);
  });

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.stopPolling();
      this.stopTeamRadioPlayback();
      if (this.resizeHandler) {
        window.removeEventListener('resize', this.resizeHandler);
      }
      if (this.fullscreenChangeHandler) {
        document.removeEventListener('fullscreenchange', this.fullscreenChangeHandler);
      }
      if (this.currentFullscreenElement() === this.trackShell?.nativeElement) {
        void this.exitFullscreen().catch(() => undefined);
      }
      this.clearCanvasRetry();
    });

    effect(() => {
      this.currentTrack();
      this.currentDrivers();
      this.activeRadioDriverNumbers();
      this.soloDriverNumber();
      this.requestTrackRender();
    });

    void this.initialize();
  }

  ngAfterViewInit(): void {
    this.requestTrackRender();
    this.resizeHandler = () => this.requestTrackRender();
    window.addEventListener('resize', this.resizeHandler);

    this.fullscreenChangeHandler = () => {
      const shell = this.trackShell?.nativeElement;
      this.isTrackFullscreen.set(Boolean(shell && this.currentFullscreenElement() === shell));
      this.requestTrackRenderBurst();
    };
    document.addEventListener('fullscreenchange', this.fullscreenChangeHandler);
    const shell = this.trackShell?.nativeElement;
    this.isTrackFullscreen.set(Boolean(shell && this.currentFullscreenElement() === shell));
  }

  async reloadAll(): Promise<void> {
    this.errorMessage.set(null);
    await this.loadBootstrap();
    await Promise.allSettled([this.refreshLive(), this.refreshWeather(), this.refreshTeamRadio()]);
  }

  async toggleTrackFullscreen(): Promise<void> {
    const shell = this.trackShell?.nativeElement;
    if (!shell) {
      return;
    }

    try {
      const activeElement = this.currentFullscreenElement();
      if (activeElement === shell) {
        await this.exitFullscreen();
        return;
      }

      await this.requestFullscreen(shell);
    } catch (error) {
      this.errorMessage.set(`Vollbild konnte nicht aktiviert werden: ${this.toErrorMessage(error)}`);
    }
  }

  toggleGlobalTeamRadio(): void {
    const next = !this.globalTeamRadioEnabled();
    this.globalTeamRadioEnabled.set(next);
    if (!next && this.soloDriverNumber() === null) {
      this.queuedTeamRadioEvents = [];
      this.stopTeamRadioPlayback();
      return;
    }
    if (next || this.soloDriverNumber() !== null) {
      void this.playQueuedTeamRadio();
    }
  }

  toggleSoloDriver(driverNumber: number | null | undefined): void {
    if (typeof driverNumber !== 'number') {
      return;
    }
    if (this.soloDriverNumber() === driverNumber) {
      this.clearSoloDriver();
      return;
    }

    this.soloDriverNumber.set(driverNumber);
    this.queuedTeamRadioEvents = [];
    this.stopTeamRadioPlayback();
    const latestEvent = this.latestTeamRadioByDriver.get(driverNumber);
    if (latestEvent) {
      this.queuedTeamRadioEvents.push(latestEvent);
      void this.playQueuedTeamRadio();
    }
  }

  clearSoloDriver(): void {
    this.soloDriverNumber.set(null);
    if (!this.globalTeamRadioEnabled()) {
      this.queuedTeamRadioEvents = [];
      this.stopTeamRadioPlayback();
      return;
    }
    void this.playQueuedTeamRadio();
  }

  isDriverRadioActive(driverNumber: number | null | undefined): boolean {
    if (typeof driverNumber !== 'number') {
      return false;
    }
    return this.activeRadioDriverNumbers().includes(driverNumber);
  }

  isDriverSolo(driverNumber: number | null | undefined): boolean {
    if (typeof driverNumber !== 'number') {
      return false;
    }
    return this.soloDriverNumber() === driverNumber;
  }

  isDriverRadioHighlighted(driverNumber: number | null | undefined): boolean {
    return this.isDriverRadioActive(driverNumber) || this.isDriverSolo(driverNumber);
  }

  trackByDriver = (_: number, driver: DriverPayload): string => {
    const number = typeof driver.driver_number === 'number' ? driver.driver_number : -1;
    return `${number}:${driver.name_acronym ?? ''}`;
  };

  trackByRadioDate = (_: number, event: TeamRadioInsightsPayload['events'][number]): string => {
    return `${event.date}:${event.driver_number}`;
  };

  formatDriverName(driver: DriverPayload): string {
    if (driver.full_name) return driver.full_name;
    const first = driver.first_name ?? '';
    const last = driver.last_name ?? '';
    const full = `${first} ${last}`.trim();
    if (full) return full;
    return driver.name_acronym ?? `Driver ${driver.driver_number ?? '?'}`;
  }

  private async initialize(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set(null);
    try {
      await this.loadBootstrap();
      await Promise.allSettled([this.refreshLive(), this.refreshWeather(), this.refreshTeamRadio()]);
      this.startPolling();
    } catch (error) {
      this.errorMessage.set(this.toErrorMessage(error));
    } finally {
      this.loading.set(false);
    }
  }

  private async loadBootstrap(): Promise<void> {
    const payload = await firstValueFrom(this.api.getBootstrap());
    this.bootstrap.set(payload);
  }

  private async refreshLive(): Promise<void> {
    const started = performance.now();
    try {
      const payload = await firstValueFrom(this.api.getLive());
      this.live.set(payload);
      this.liveUnavailable.set(false);
      this.liveLatencyMs.set(Math.round(performance.now() - started));
    } catch (error) {
      const status = this.httpStatus(error);
      if (status === 503) {
        this.liveUnavailable.set(true);
        return;
      }
      this.errorMessage.set(`Live-Update fehlgeschlagen: ${this.toErrorMessage(error)}`);
    }
  }

  private async refreshWeather(): Promise<void> {
    try {
      const payload = await firstValueFrom(this.api.getWeather());
      this.weather.set(payload);
    } catch (error) {
      this.errorMessage.set(`Wetter konnte nicht geladen werden: ${this.toErrorMessage(error)}`);
    }
  }

  private async refreshTeamRadio(): Promise<void> {
    try {
      const payload = await firstValueFrom(this.api.getTeamRadio(TEAM_RADIO_LIMIT));
      this.teamRadio.set(payload);
      this.handleTeamRadioPayload(payload);
    } catch (error) {
      this.errorMessage.set(`Team Radio konnte nicht geladen werden: ${this.toErrorMessage(error)}`);
    }
  }

  private startPolling(): void {
    this.stopPolling();
    this.pollHandles.push(window.setInterval(() => void this.refreshLive(), LIVE_POLL_INTERVAL_MS));
    this.pollHandles.push(window.setInterval(() => void this.refreshWeather(), WEATHER_POLL_INTERVAL_MS));
    this.pollHandles.push(window.setInterval(() => void this.refreshTeamRadio(), TEAM_RADIO_POLL_INTERVAL_MS));
    this.pollHandles.push(window.setInterval(() => this.heartbeatTick(), TEAM_RADIO_ACTIVITY_TICK_MS));
  }

  private stopPolling(): void {
    for (const handle of this.pollHandles) {
      window.clearInterval(handle);
    }
    this.pollHandles = [];
  }

  private handleTeamRadioPayload(payload: TeamRadioInsightsPayload): void {
    if (this.teamRadioSessionKey !== payload.session_key) {
      this.teamRadioSessionKey = payload.session_key;
      this.resetTeamRadioTracking();
      this.soloDriverNumber.set(null);
    }

    const sortedEvents = [...(payload.events ?? [])].sort(
      (left, right) => Date.parse(left.date) - Date.parse(right.date),
    );

    const now = Date.now();
    for (const event of sortedEvents) {
      const driverNumber = event.driver_number;
      if (typeof driverNumber !== 'number') {
        continue;
      }

      this.latestTeamRadioByDriver.set(driverNumber, event);
      const eventKey = this.teamRadioEventKey(event);
      const eventMs = Date.parse(event.date);
      const until = Number.isFinite(eventMs)
        ? eventMs + TEAM_RADIO_ACTIVE_WINDOW_MS
        : now + TEAM_RADIO_ACTIVE_WINDOW_MS;
      if (until > now) {
        const previousUntil = this.activeRadioUntilByDriver.get(driverNumber) ?? 0;
        this.activeRadioUntilByDriver.set(driverNumber, Math.max(previousUntil, until));
      }

      if (this.seenTeamRadioEventKeys.has(eventKey)) {
        continue;
      }

      this.seenTeamRadioEventKeys.add(eventKey);
      this.trimSeenTeamRadioEventKeys();
      if (this.shouldPlayTeamRadioEvent(event)) {
        this.queuedTeamRadioEvents.push(event);
      }
    }

    this.pruneAndPublishActiveRadioDrivers();
    void this.playQueuedTeamRadio();
  }

  private resetTeamRadioTracking(): void {
    this.queuedTeamRadioEvents = [];
    this.seenTeamRadioEventKeys.clear();
    this.activeRadioUntilByDriver.clear();
    this.latestTeamRadioByDriver.clear();
    this.activeRadioDriverNumbers.set([]);
    this.nowTalkingDriverNumber.set(null);
    this.stopTeamRadioPlayback();
  }

  private trimSeenTeamRadioEventKeys(): void {
    while (this.seenTeamRadioEventKeys.size > TEAM_RADIO_SEEN_LIMIT) {
      const firstKey = this.seenTeamRadioEventKeys.values().next().value;
      if (typeof firstKey !== 'string') {
        return;
      }
      this.seenTeamRadioEventKeys.delete(firstKey);
    }
  }

  private shouldPlayTeamRadioEvent(event: TeamRadioEventPayload): boolean {
    const solo = this.soloDriverNumber();
    if (solo !== null) {
      return event.driver_number === solo;
    }
    return this.globalTeamRadioEnabled();
  }

  private pruneAndPublishActiveRadioDrivers(): void {
    const now = Date.now();
    for (const [driverNumber, until] of this.activeRadioUntilByDriver) {
      if (until <= now) {
        this.activeRadioUntilByDriver.delete(driverNumber);
      }
    }

    const activeNumbers = [...this.activeRadioUntilByDriver.keys()];
    this.activeRadioDriverNumbers.set(activeNumbers);

    let currentTalker: number | null = null;
    let newestTalkMs = Number.NEGATIVE_INFINITY;
    for (const driverNumber of activeNumbers) {
      const event = this.latestTeamRadioByDriver.get(driverNumber);
      if (!event) continue;
      const eventMs = Date.parse(event.date);
      if (!Number.isFinite(eventMs)) continue;
      if (eventMs > newestTalkMs) {
        newestTalkMs = eventMs;
        currentTalker = driverNumber;
      }
    }
    this.nowTalkingDriverNumber.set(currentTalker);
  }

  private teamRadioEventKey(event: TeamRadioEventPayload): string {
    return `${event.driver_number}:${event.date}:${event.recording_url}`;
  }

  private formatDuration(durationMs: number): string {
    const totalSeconds = Math.floor(Math.max(0, durationMs) / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
  }

  private ensureAudioElement(): HTMLAudioElement {
    if (!this.audioElement) {
      this.audioElement = new Audio();
      this.audioElement.preload = 'none';
    }
    return this.audioElement;
  }

  private stopTeamRadioPlayback(): void {
    this.isTeamRadioPlaybackRunning = false;
    const audio = this.audioElement;
    if (!audio) return;
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
  }

  private async playQueuedTeamRadio(): Promise<void> {
    if (this.isTeamRadioPlaybackRunning) {
      return;
    }
    if (this.queuedTeamRadioEvents.length === 0) {
      return;
    }

    this.isTeamRadioPlaybackRunning = true;
    try {
      while (this.queuedTeamRadioEvents.length > 0) {
        const event = this.queuedTeamRadioEvents.shift();
        if (!event) continue;
        if (!this.shouldPlayTeamRadioEvent(event)) continue;
        const source = event.recording_url;
        if (!source) continue;
        const played = await this.playTeamRadioClip(source);
        if (!played) {
          break;
        }
      }
    } finally {
      this.isTeamRadioPlaybackRunning = false;
    }
  }

  private async playTeamRadioClip(source: string): Promise<boolean> {
    const audio = this.ensureAudioElement();
    audio.pause();
    audio.src = source;
    audio.currentTime = 0;

    return new Promise<boolean>((resolve) => {
      let resolved = false;
      const complete = (result: boolean): void => {
        if (resolved) return;
        resolved = true;
        audio.onended = null;
        audio.onerror = null;
        resolve(result);
      };

      audio.onended = () => complete(true);
      audio.onerror = () => complete(false);

      const playPromise = audio.play();
      if (playPromise) {
        playPromise.catch(() => complete(false));
      }
    });
  }

  private requestTrackRender(): void {
    requestAnimationFrame(() => this.renderTrackCanvas());
  }

  private requestTrackRenderBurst(): void {
    this.requestTrackRender();
    window.setTimeout(() => this.requestTrackRender(), 80);
    window.setTimeout(() => this.requestTrackRender(), 220);
  }

  private heartbeatTick(): void {
    this.heartbeatNowMs.set(Date.now());
    this.pruneAndPublishActiveRadioDrivers();
  }

  private scheduleCanvasRetry(): void {
    if (this.canvasRetryHandle !== null) return;
    this.canvasRetryHandle = window.setTimeout(() => {
      this.canvasRetryHandle = null;
      this.requestTrackRender();
    }, 120);
  }

  private clearCanvasRetry(): void {
    if (this.canvasRetryHandle === null) return;
    window.clearTimeout(this.canvasRetryHandle);
    this.canvasRetryHandle = null;
  }

  private renderTrackCanvas(): void {
    const canvas = this.trackCanvas?.nativeElement;
    if (!canvas) return;

    const points = this.currentTrack();
    const drivers = this.currentDrivers();
    const context = canvas.getContext('2d');
    if (!context) return;

    const rect = canvas.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      this.scheduleCanvasRetry();
      return;
    }
    this.clearCanvasRetry();

    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.floor(rect.width * ratio);
    canvas.height = Math.floor(rect.height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, rect.width, rect.height);

    if (points.length < 2) {
      return;
    }

    const bounds = this.pointsBounds(points);
    const edgePadding = this.isTrackFullscreen() ? 2 : 14;
    const projector = this.projector(bounds, rect.width, rect.height, edgePadding);

    context.lineJoin = 'round';
    context.lineCap = 'round';

    context.beginPath();
    const firstPoint = projector(points[0]);
    context.moveTo(firstPoint.x, firstPoint.y);
    for (let index = 1; index < points.length; index += 1) {
      const point = projector(points[index]);
      context.lineTo(point.x, point.y);
    }
    context.strokeStyle = '#2f3647';
    context.lineWidth = 10;
    context.stroke();

    context.beginPath();
    context.moveTo(firstPoint.x, firstPoint.y);
    for (let index = 1; index < points.length; index += 1) {
      const point = projector(points[index]);
      context.lineTo(point.x, point.y);
    }
    context.strokeStyle = '#f74c68';
    context.lineWidth = 2;
    context.stroke();

    const markerKeys = new Set<string>();
    const renderDrivers = [...drivers].sort((a, b) => {
      const posA = typeof a.current_position === 'number' ? a.current_position : 999;
      const posB = typeof b.current_position === 'number' ? b.current_position : 999;
      return posA - posB;
    });

    for (const driver of renderDrivers) {
      const marker = driver.track_point;
      if (!marker || !this.isTrackPoint(marker)) continue;
      if (typeof driver.current_position !== 'number') continue;
      const markerKey = `${marker.x}:${marker.y}:${marker.z}`;
      if (markerKeys.has(markerKey)) continue;
      markerKeys.add(markerKey);
      const point = projector(marker);
      const color = this.driverColor(driver);
      const label = driver.name_acronym ?? String(driver.driver_number ?? '?');
      const radioActive = this.isDriverRadioActive(driver.driver_number);
      const radioSolo = this.isDriverSolo(driver.driver_number);
      const radioHighlighted = radioActive || radioSolo;

      context.beginPath();
      context.arc(point.x, point.y, 6, 0, Math.PI * 2);
      context.fillStyle = color;
      context.fill();
      context.lineWidth = 2;
      context.strokeStyle = '#0d1118';
      context.stroke();

      context.fillStyle = '#edf1ff';
      context.font = '10px "Segoe UI", sans-serif';
      context.textAlign = 'left';
      context.fillText(label, point.x + 8, point.y + 4);

      if (radioHighlighted) {
        context.beginPath();
        context.arc(point.x, point.y, radioSolo ? 12 : 10, 0, Math.PI * 2);
        context.strokeStyle = radioSolo ? '#7ee7ff' : '#dfff7f';
        context.lineWidth = 2;
        context.stroke();

        context.fillStyle = radioSolo ? '#b7f3ff' : '#f7ffb5';
        context.font = '11px "Segoe UI Emoji", "Segoe UI Symbol", "Segoe UI", sans-serif';
        context.fillText('🔊', point.x + 8, point.y - 8);
      }
    }
  }

  private pointsBounds(points: TrackPoint[]): { minX: number; maxX: number; minY: number; maxY: number } {
    const xs = points.map((point) => point.x);
    const ys = points.map((point) => point.y);
    return {
      minX: Math.min(...xs),
      maxX: Math.max(...xs),
      minY: Math.min(...ys),
      maxY: Math.max(...ys),
    };
  }

  private projector(
    bounds: { minX: number; maxX: number; minY: number; maxY: number },
    width: number,
    height: number,
    edgePadding: number,
  ): (point: TrackPoint) => { x: number; y: number } {
    const padding = Math.max(0, edgePadding);
    const spanX = Math.max(1, bounds.maxX - bounds.minX);
    const spanY = Math.max(1, bounds.maxY - bounds.minY);
    const drawWidth = Math.max(1, width - 2 * padding);
    const drawHeight = Math.max(1, height - 2 * padding);
    const scale = Math.min(drawWidth / spanX, drawHeight / spanY);
    const offsetX = (width - spanX * scale) / 2;
    const offsetY = (height - spanY * scale) / 2;

    return (point: TrackPoint) => {
      const x = (point.x - bounds.minX) * scale + offsetX;
      const y = height - ((point.y - bounds.minY) * scale + offsetY);
      return { x, y };
    };
  }

  private isTrackPoint(value: unknown): value is TrackPoint {
    if (typeof value !== 'object' || value === null) return false;
    const candidate = value as { x?: unknown; y?: unknown; z?: unknown };
    return (
      typeof candidate.x === 'number' &&
      typeof candidate.y === 'number' &&
      typeof candidate.z === 'number'
    );
  }

  private driverColor(driver: DriverPayload): string {
    const raw = driver.team_colour;
    if (!raw || typeof raw !== 'string') {
      return '#fbc02d';
    }
    return `#${raw.replace('#', '')}`;
  }

  private normalizeDrivers(drivers: DriverPayload[]): DriverPayload[] {
    const byNumber = new Map<number, DriverPayload>();
    for (const driver of drivers) {
      const driverNumber = driver.driver_number;
      if (typeof driverNumber !== 'number') continue;

      const existing = byNumber.get(driverNumber);
      if (!existing) {
        byNumber.set(driverNumber, driver);
        continue;
      }

      const existingTs = this.driverRecencyMs(existing);
      const nextTs = this.driverRecencyMs(driver);
      if (nextTs >= existingTs) {
        byNumber.set(driverNumber, { ...existing, ...driver });
      }
    }
    return [...byNumber.values()];
  }

  private driverRecencyMs(driver: DriverPayload): number {
    const trackDate = driver.track_point?.date;
    if (typeof trackDate === 'string') {
      const ms = Date.parse(trackDate);
      if (Number.isFinite(ms)) return ms;
    }
    if (typeof driver.position_date === 'string') {
      const ms = Date.parse(driver.position_date);
      if (Number.isFinite(ms)) return ms;
    }
    if (typeof driver.lap_date === 'string') {
      const ms = Date.parse(driver.lap_date);
      if (Number.isFinite(ms)) return ms;
    }
    return Number.NEGATIVE_INFINITY;
  }

  private currentFullscreenElement(): Element | null {
    const doc = document as Document & { webkitFullscreenElement?: Element | null };
    return document.fullscreenElement ?? doc.webkitFullscreenElement ?? null;
  }

  private async requestFullscreen(element: HTMLElement): Promise<void> {
    const candidate = element as HTMLElement & {
      webkitRequestFullscreen?: () => Promise<void> | void;
    };

    if (typeof candidate.requestFullscreen === 'function') {
      await candidate.requestFullscreen();
      return;
    }

    if (typeof candidate.webkitRequestFullscreen === 'function') {
      await Promise.resolve(candidate.webkitRequestFullscreen());
      return;
    }

    throw new Error('Fullscreen API wird vom Browser nicht unterstuetzt.');
  }

  private async exitFullscreen(): Promise<void> {
    const doc = document as Document & {
      webkitExitFullscreen?: () => Promise<void> | void;
    };

    if (typeof document.exitFullscreen === 'function') {
      await document.exitFullscreen();
      return;
    }

    if (typeof doc.webkitExitFullscreen === 'function') {
      await Promise.resolve(doc.webkitExitFullscreen());
      return;
    }
  }

  private httpStatus(error: unknown): number | null {
    if (typeof error !== 'object' || error === null) return null;
    if (!('status' in error)) return null;
    const value = (error as { status?: unknown }).status;
    return typeof value === 'number' ? value : null;
  }

  private toErrorMessage(error: unknown): string {
    if (this.isApiProxyHtmlResponse(error)) {
      return 'API endpoint returned HTML instead of JSON. Check OpenF1ApiService base URL and backend availability.';
    }
    if (typeof error === 'string') return error;
    if (error instanceof Error && error.message) return error.message;
    if (typeof error === 'object' && error !== null && 'message' in error) {
      const message = (error as { message?: unknown }).message;
      if (typeof message === 'string' && message) return message;
    }
    return 'Unbekannter Fehler';
  }

  private isApiProxyHtmlResponse(error: unknown): boolean {
    if (typeof error !== 'object' || error === null) return false;
    const candidate = error as { error?: unknown; status?: unknown };
    if (candidate.status !== 200) return false;
    if (typeof candidate.error !== 'object' || candidate.error === null) return false;
    const nested = candidate.error as { text?: unknown };
    if (typeof nested.text !== 'string') return false;
    const text = nested.text.toLowerCase();
    return text.includes('<!doctype html') || text.includes('<html');
  }
}
