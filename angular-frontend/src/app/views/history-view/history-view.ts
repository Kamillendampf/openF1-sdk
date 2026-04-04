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
  HistoryReplayEventPayload,
  HistoryReplayInitPayload,
  HistoryReplayLapPayload,
  HistorySessionSummary,
  TrackPoint,
} from '../../core/openf1.models';

const HISTORY_STEP_DURATION_MS = 1000;
const HISTORY_MIN_STEP_DURATION_MS = 125;
const HISTORY_SAMPLE_STEP = 1;

type HistoryPlaybackFrame = {
  timestamp: string | null;
  events: HistoryReplayEventPayload[];
};

type DriverAnimationState = {
  from: TrackPoint;
  to: TrackPoint;
  startedAtMs: number;
  durationMs: number;
};

type DriverTimedEvent = {
  timestampMs: number;
  event: HistoryReplayEventPayload;
};

@Component({
  selector: 'app-history-view',
  imports: [CommonModule],
  templateUrl: './history-view.html',
  styleUrl: './history-view.scss',
})
export class HistoryViewComponent implements AfterViewInit {
  private readonly api = inject(OpenF1ApiService);
  private readonly destroyRef = inject(DestroyRef);

  @ViewChild('trackShell') private trackShell?: ElementRef<HTMLElement>;
  @ViewChild('trackCanvas') private trackCanvas?: ElementRef<HTMLCanvasElement>;

  readonly loading = signal(true);
  readonly sessionsLoading = signal(false);
  readonly replayLoading = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly metaMessage = signal('Noch keine historische Session geladen.');

  readonly currentYear = signal(new Date().getFullYear());
  readonly sessions = signal<HistorySessionSummary[]>([]);
  readonly selectedSessionKey = signal<number | null>(null);
  readonly replayInit = signal<HistoryReplayInitPayload | null>(null);
  readonly drivers = signal<DriverPayload[]>([]);
  readonly currentLap = signal(1);
  readonly playbackPaused = signal(false);
  readonly playbackSpeed = signal(1);
  readonly timelinePreviewLap = signal<number | null>(null);
  readonly globalTeamRadioEnabled = signal(true);

  readonly yearOptions = this.buildYearOptions();

  readonly currentTrack = computed<TrackPoint[]>(() => {
    const track = this.replayInit()?.track;
    return Array.isArray(track) ? track : [];
  });

  readonly sessionTitle = computed<string>(() => {
    const replay = this.replayInit();
    if (!replay) return 'Keine historische Session';
    return `${replay.circuit_name} - ${replay.session_name}`;
  });

  readonly lapNumbers = computed<number[]>(() => {
    const numbers = this.replayInit()?.replay?.lap_numbers;
    return Array.isArray(numbers) ? numbers : [];
  });

  readonly firstLap = computed<number>(() => {
    const laps = this.lapNumbers();
    return laps.length ? laps[0] : 1;
  });

  readonly lastLap = computed<number>(() => {
    const laps = this.lapNumbers();
    return laps.length ? laps[laps.length - 1] : 1;
  });

  readonly lapMax = computed<number | null>(() => {
    const max = this.replayInit()?.lap?.max;
    return typeof max === 'number' ? max : null;
  });

  readonly lapDisplay = computed<string>(() => {
    const max = this.lapMax();
    return max !== null ? `${this.currentLap()}/${max}` : `${this.currentLap()}/-`;
  });

  readonly timelineLap = computed<number>(() => this.timelinePreviewLap() ?? this.currentLap());

  readonly driversSorted = computed<DriverPayload[]>(() => {
    return [...this.drivers()].sort((a, b) => {
      const posA = typeof a.current_position === 'number' ? a.current_position : 999;
      const posB = typeof b.current_position === 'number' ? b.current_position : 999;
      if (posA !== posB) return posA - posB;
      const numA = typeof a.driver_number === 'number' ? a.driver_number : 999;
      const numB = typeof b.driver_number === 'number' ? b.driver_number : 999;
      return numA - numB;
    });
  });

  readonly canStepBack = computed<boolean>(() => {
    return this.previousLapNumber() !== null && !this.replayLoading();
  });

  readonly canStepForward = computed<boolean>(() => {
    return this.nextLapNumber() !== null && !this.replayLoading();
  });

  readonly hasReplay = computed<boolean>(() => {
    return this.lapNumbers().length > 0 && this.selectedSessionKey() !== null;
  });

  private baseDrivers: DriverPayload[] = [];
  private lapCache = new Map<number, HistoryReplayLapPayload>();
  private lapLoadPromises = new Map<number, Promise<HistoryReplayLapPayload>>();
  private prefetchGeneration = 0;
  private playbackFrames: HistoryPlaybackFrame[] = [];
  private playbackFrameIndex = 0;
  private playbackTimeoutId: number | null = null;
  private lastPlaybackDelayMs = HISTORY_STEP_DURATION_MS;
  private canvasRetryHandle: number | null = null;
  private resizeHandler: (() => void) | null = null;
  private fullscreenChangeHandler: (() => void) | null = null;
  private lastKnownTrackPointByDriver = new Map<number, TrackPoint>();
  private trackRenderQueued = false;
  private driverAnimationByNumber = new Map<number, DriverAnimationState>();
  readonly isTrackFullscreen = signal(false);

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.stopPlayback();
      if (this.resizeHandler) {
        window.removeEventListener('resize', this.resizeHandler);
      }
      if (this.fullscreenChangeHandler) {
        document.removeEventListener('fullscreenchange', this.fullscreenChangeHandler);
      }
      if (document.fullscreenElement === this.trackShell?.nativeElement) {
        void document.exitFullscreen().catch(() => undefined);
      }
      this.clearCanvasRetry();
    });

    effect(() => {
      this.currentTrack();
      this.drivers();
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

  trackByDriver = (_: number, driver: DriverPayload): string => {
    const number = typeof driver.driver_number === 'number' ? driver.driver_number : -1;
    return `${number}:${driver.name_acronym ?? ''}`;
  };

  formatDriverName(driver: DriverPayload): string {
    if (driver.full_name) return driver.full_name;
    const first = driver.first_name ?? '';
    const last = driver.last_name ?? '';
    const full = `${first} ${last}`.trim();
    if (full) return full;
    return driver.name_acronym ?? `Driver ${driver.driver_number ?? '?'}`;
  }

  formatSessionLabel(session: HistorySessionSummary): string {
    const date = this.safeDateTime(session.date_start);
    const prefix = date ? `${date} | ` : '';
    return `${prefix}${session.circuit_name} | ${session.session_name}`;
  }

  async reloadCurrentSession(): Promise<void> {
    await this.loadSelectedSession();
  }

  async stepLap(delta: number): Promise<void> {
    const target = this.currentLap() + delta;
    if (!this.lapNumbers().includes(target)) {
      return;
    }
    await this.seekLap(target);
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
    this.globalTeamRadioEnabled.set(!this.globalTeamRadioEnabled());
  }

  togglePlayback(): void {
    if (this.playbackPaused()) {
      this.resumePlayback();
    } else {
      this.pausePlayback();
    }
  }

  onYearChange(event: Event): void {
    const value = Number.parseInt((event.target as HTMLSelectElement).value, 10);
    if (!Number.isInteger(value)) {
      return;
    }
    this.currentYear.set(value);
    void this.changeYear();
  }

  onSessionChange(event: Event): void {
    const value = Number.parseInt((event.target as HTMLSelectElement).value, 10);
    if (!Number.isInteger(value)) {
      this.selectedSessionKey.set(null);
      return;
    }
    this.selectedSessionKey.set(value);
    void this.loadSelectedSession();
  }

  onSpeedChange(event: Event): void {
    const speed = Number.parseInt((event.target as HTMLSelectElement).value, 10);
    this.playbackSpeed.set(Number.isFinite(speed) && speed > 0 ? speed : 1);
  }

  onTimelineInput(event: Event): void {
    const lap = Number.parseInt((event.target as HTMLInputElement).value, 10);
    this.timelinePreviewLap.set(Number.isInteger(lap) ? lap : null);
  }

  onTimelineChange(event: Event): void {
    const lap = Number.parseInt((event.target as HTMLInputElement).value, 10);
    this.timelinePreviewLap.set(null);
    if (!Number.isInteger(lap)) {
      return;
    }
    void this.seekLap(lap);
  }

  private async initialize(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set(null);
    try {
      await this.loadSessions();
      await this.loadSelectedSession();
    } catch (error) {
      this.errorMessage.set(this.toErrorMessage(error));
    } finally {
      this.loading.set(false);
    }
  }

  private async changeYear(): Promise<void> {
    this.errorMessage.set(null);
    try {
      await this.loadSessions();
      await this.loadSelectedSession();
    } catch (error) {
      this.errorMessage.set(this.toErrorMessage(error));
    }
  }

  private async loadSessions(): Promise<void> {
    this.sessionsLoading.set(true);
    this.metaMessage.set('Lade historische Sessions...');
    try {
      const payload = await firstValueFrom(this.api.getHistorySessions(this.currentYear(), 120));
      const sessions = Array.isArray(payload.sessions) ? payload.sessions : [];
      this.sessions.set(sessions);

      if (!sessions.length) {
        this.selectedSessionKey.set(null);
        this.clearReplayState();
        this.metaMessage.set('Keine historischen Sessions gefunden.');
        return;
      }

      const selected = this.selectedSessionKey();
      if (!selected || !sessions.some((session) => session.session_key === selected)) {
        this.selectedSessionKey.set(sessions[0].session_key);
      }
      this.metaMessage.set(`${sessions.length} historische Sessions geladen.`);
    } finally {
      this.sessionsLoading.set(false);
    }
  }

  private async loadSelectedSession(): Promise<void> {
    const sessionKey = this.selectedSessionKey();
    if (!sessionKey) {
      return;
    }
    this.errorMessage.set(null);
    this.stopPlayback();
    this.lapCache.clear();
    this.lapLoadPromises.clear();
    const generation = ++this.prefetchGeneration;
    this.playbackPaused.set(false);
    this.timelinePreviewLap.set(null);

    this.replayLoading.set(true);
    this.metaMessage.set('Lade historische Replay-Metadaten...');
    try {
      const payload = await firstValueFrom(this.api.getHistoryReplayInit(sessionKey));
      this.applyReplayInit(payload);
    } finally {
      this.replayLoading.set(false);
    }

    const firstLap = this.firstLap();
    await this.loadLapAndPlay(firstLap, generation);
  }

  private clearReplayState(): void {
    this.stopPlayback();
    this.replayInit.set(null);
    this.baseDrivers = [];
    this.drivers.set([]);
    this.driverAnimationByNumber.clear();
    this.lastKnownTrackPointByDriver.clear();
    this.lapLoadPromises.clear();
    this.prefetchGeneration += 1;
    this.currentLap.set(1);
    this.timelinePreviewLap.set(null);
    this.lapCache.clear();
  }

  private applyReplayInit(payload: HistoryReplayInitPayload): void {
    this.replayInit.set(payload);
    const firstLap = Array.isArray(payload.replay?.lap_numbers) && payload.replay.lap_numbers.length
      ? payload.replay.lap_numbers[0]
      : 1;
    this.currentLap.set(firstLap);

    const sourceDrivers = Array.isArray(payload.drivers) ? payload.drivers : [];
    this.lastKnownTrackPointByDriver.clear();
    this.baseDrivers = sourceDrivers.map((driver) => {
      const number = typeof driver.driver_number === 'number' ? driver.driver_number : null;
      const marker = driver.track_point;
      const seed = marker && this.isTrackPoint(marker) ? marker : null;
      if (number !== null && seed) {
        this.lastKnownTrackPointByDriver.set(number, seed);
      }
      return {
        ...driver,
        track_point: seed,
        current_lap: firstLap,
        lap_date: null,
      };
    });
    this.drivers.set(this.baseDrivers.map((driver) => ({ ...driver })));

    const startDate = this.safeDateTime(payload.date_start);
    this.metaMessage.set(startDate ? `Historisch - ${startDate}` : 'Historischer Replay initialisiert.');
  }

  private async loadLapAndPlay(lapNumber: number, generation: number = this.prefetchGeneration): Promise<void> {
    const sessionKey = this.selectedSessionKey();
    if (!sessionKey || !this.lapNumbers().includes(lapNumber)) {
      return;
    }

    this.replayLoading.set(true);
    this.stopPlayback();
    this.metaMessage.set(`Lade Lap ${lapNumber}...`);
    try {
      const lapPayload = await this.getOrLoadLapPayload(sessionKey, lapNumber, generation);
      if (generation !== this.prefetchGeneration) {
        return;
      }

      this.currentLap.set(lapNumber);
      const events = Array.isArray(lapPayload.playback?.events) ? lapPayload.playback.events : [];
      this.resetDriversForLap(lapNumber, events);
      if (!events.length) {
        const nextLap = this.lapNumbers().find((lap) => lap > lapNumber) ?? null;
        if (nextLap !== null && !this.playbackPaused()) {
          this.metaMessage.set(`Lap ${lapNumber} ohne Bewegungsdaten, springe zu Lap ${nextLap}...`);
          await this.loadLapAndPlay(nextLap, generation);
          return;
        }
      }
      this.startPlayback(events);
      this.prefetchUpcomingLaps(lapNumber, generation);
    } finally {
      this.replayLoading.set(false);
    }
  }

  private resetDriversForLap(lapNumber: number, events: HistoryReplayEventPayload[]): void {
    this.driverAnimationByNumber.clear();
    const firstEventByDriver = new Map<number, HistoryReplayEventPayload>();
    for (const event of events) {
      if (!firstEventByDriver.has(event.driver_number)) {
        firstEventByDriver.set(event.driver_number, event);
      }
    }

    this.drivers.set(
      this.baseDrivers.map((driver) => ({
        ...driver,
        track_point: this.seedTrackPointForLap(driver.driver_number, firstEventByDriver),
        current_position: this.seedPositionForLap(driver, firstEventByDriver),
        position_date: this.seedPositionDateForLap(driver, firstEventByDriver),
        current_lap: lapNumber,
        lap_date: null,
      })),
    );
  }

  private seedTrackPointForLap(
    driverNumber: number | undefined,
    firstEventByDriver: Map<number, HistoryReplayEventPayload>,
  ): TrackPoint | null {
    if (typeof driverNumber !== 'number') {
      return null;
    }
    const lapSeed = firstEventByDriver.get(driverNumber);
    if (lapSeed) {
      return { x: lapSeed.x, y: lapSeed.y, z: lapSeed.z };
    }
    return this.lastKnownTrackPointByDriver.get(driverNumber) ?? null;
  }

  private seedPositionForLap(
    driver: DriverPayload,
    firstEventByDriver: Map<number, HistoryReplayEventPayload>,
  ): number | null {
    const number = driver.driver_number;
    if (typeof number !== 'number') {
      return typeof driver.current_position === 'number' ? driver.current_position : null;
    }
    const firstEvent = firstEventByDriver.get(number);
    if (firstEvent && typeof firstEvent.position === 'number') {
      return firstEvent.position;
    }
    return typeof driver.current_position === 'number' ? driver.current_position : null;
  }

  private seedPositionDateForLap(
    driver: DriverPayload,
    firstEventByDriver: Map<number, HistoryReplayEventPayload>,
  ): string | null {
    const number = driver.driver_number;
    if (typeof number !== 'number') {
      return typeof driver.position_date === 'string' ? driver.position_date : null;
    }
    const firstEvent = firstEventByDriver.get(number);
    if (firstEvent && typeof firstEvent.position_date === 'string') {
      return firstEvent.position_date;
    }
    return typeof driver.position_date === 'string' ? driver.position_date : null;
  }

  private startPlayback(events: HistoryReplayEventPayload[]): void {
    this.playbackFrames = this.buildPlaybackFrames(events);
    this.playbackFrameIndex = 0;

    if (!this.playbackFrames.length) {
      this.metaMessage.set(`Lap ${this.currentLap()} geladen, aber ohne Bewegungsdaten.`);
      return;
    }

    this.metaMessage.set(`Replay Lap ${this.currentLap()} gestartet (${this.playbackSpeed()}x).`);
    if (!this.playbackPaused()) {
      this.runPlayback();
    }
  }

  private runPlayback = (): void => {
    if (this.playbackPaused()) {
      return;
    }

    if (this.playbackFrameIndex >= this.playbackFrames.length) {
      this.stopPlayback();
      const nextLap = this.nextLapNumber();
      if (nextLap !== null && !this.playbackPaused()) {
        void this.loadLapAndPlay(nextLap);
      } else {
        this.metaMessage.set('Historischer Replay abgeschlossen.');
      }
      return;
    }

    const currentFrame = this.playbackFrames[this.playbackFrameIndex];
    this.applyHistoryEvents(currentFrame.events);
    this.playbackFrameIndex += 1;
    if (this.playbackFrames.length - this.playbackFrameIndex <= 10) {
      this.prefetchUpcomingLaps(this.currentLap(), this.prefetchGeneration);
    }

    const progress = Math.min(100, Math.round((this.playbackFrameIndex / this.playbackFrames.length) * 100));
    const ts = this.safeTime(currentFrame.timestamp);
    if (ts) {
      this.metaMessage.set(`Lap ${this.currentLap()} - ${progress}% - ${ts} (${this.playbackSpeed()}x)`);
    } else {
      this.metaMessage.set(`Lap ${this.currentLap()} - ${progress}% (${this.playbackSpeed()}x)`);
    }

    this.lastPlaybackDelayMs = this.playbackStepDelayMs();
    this.playbackTimeoutId = window.setTimeout(this.runPlayback, this.lastPlaybackDelayMs);
  };

  private pausePlayback(): void {
    this.playbackPaused.set(true);
    if (this.playbackTimeoutId !== null) {
      window.clearTimeout(this.playbackTimeoutId);
      this.playbackTimeoutId = null;
    }
  }

  private resumePlayback(): void {
    this.playbackPaused.set(false);
    if (this.playbackFrames.length > 0 && this.playbackFrameIndex < this.playbackFrames.length) {
      this.runPlayback();
      return;
    }
    void this.loadLapAndPlay(this.currentLap());
  }

  private stopPlayback(): void {
    if (this.playbackTimeoutId !== null) {
      window.clearTimeout(this.playbackTimeoutId);
      this.playbackTimeoutId = null;
    }
    this.playbackFrames = [];
    this.playbackFrameIndex = 0;
    this.driverAnimationByNumber.clear();
  }

  private async seekLap(lapNumber: number): Promise<void> {
    if (!this.lapNumbers().includes(lapNumber)) {
      return;
    }
    const wasPaused = this.playbackPaused();
    this.stopPlayback();
    this.playbackPaused.set(wasPaused);
    await this.loadLapAndPlay(lapNumber, this.prefetchGeneration);
  }

  private applyHistoryEvents(events: HistoryReplayEventPayload[]): void {
    if (!events.length) {
      return;
    }

    const drivers = this.drivers();
    if (!drivers.length) {
      return;
    }

    const indexByDriverNumber = new Map<number, number>();
    for (let index = 0; index < drivers.length; index += 1) {
      const number = drivers[index].driver_number;
      if (typeof number === 'number') {
        indexByDriverNumber.set(number, index);
      }
    }

    const nextDrivers = [...drivers];
    const nowMs = performance.now();
    const stepDurationMs = this.playbackStepDelayMs();
    let lapFromEvents = this.currentLap();

    for (const event of events) {
      const index = indexByDriverNumber.get(event.driver_number);
      if (typeof index !== 'number') {
        continue;
      }

      const previous = nextDrivers[index];
      const targetPoint: TrackPoint = {
        x: event.x,
        y: event.y,
        z: event.z,
      };
      const renderedPoint = this.currentRenderedPoint(previous, nowMs);
      const fromPoint = renderedPoint ?? (previous.track_point && this.isTrackPoint(previous.track_point)
        ? { x: previous.track_point.x, y: previous.track_point.y, z: previous.track_point.z }
        : targetPoint);

      this.driverAnimationByNumber.set(event.driver_number, {
        from: fromPoint,
        to: targetPoint,
        startedAtMs: nowMs,
        durationMs: stepDurationMs,
      });

      nextDrivers[index] = {
        ...previous,
        track_point: {
          x: event.x,
          y: event.y,
          z: event.z,
          date: event.date,
        },
        current_position: typeof event.position === 'number' ? event.position : previous.current_position,
        position_date: typeof event.position_date === 'string' ? event.position_date : previous.position_date,
        current_lap: event.lap_number,
        lap_date: event.date,
      };

      this.lastKnownTrackPointByDriver.set(event.driver_number, targetPoint);
      if (event.lap_number > lapFromEvents) {
        lapFromEvents = event.lap_number;
      }
    }

    this.drivers.set(nextDrivers);
    if (lapFromEvents > 0) {
      this.currentLap.set(lapFromEvents);
    }
    this.requestTrackRender();
  }

  private previousLapNumber(): number | null {
    const laps = this.lapNumbers();
    const current = this.currentLap();
    const index = laps.indexOf(current);
    if (index <= 0) return null;
    return laps[index - 1];
  }

  private nextLapNumber(): number | null {
    const laps = this.lapNumbers();
    const current = this.currentLap();
    const index = laps.indexOf(current);
    if (index === -1 || index >= laps.length - 1) return null;
    return laps[index + 1];
  }

  private buildPlaybackFrames(events: HistoryReplayEventPayload[]): HistoryPlaybackFrame[] {
    if (!Array.isArray(events) || !events.length) {
      return [];
    }

    const byDriver = new Map<number, DriverTimedEvent[]>();
    let firstMs = Number.POSITIVE_INFINITY;
    let lastMs = Number.NEGATIVE_INFINITY;

    for (const event of events) {
      if (typeof event.driver_number !== 'number') {
        continue;
      }
      const timestampMs = Date.parse(event.date);
      if (!Number.isFinite(timestampMs)) {
        continue;
      }
      if (!byDriver.has(event.driver_number)) {
        byDriver.set(event.driver_number, []);
      }
      byDriver.get(event.driver_number)?.push({ timestampMs, event });
      if (timestampMs < firstMs) firstMs = timestampMs;
      if (timestampMs > lastMs) lastMs = timestampMs;
    }

    if (!Number.isFinite(firstMs) || !Number.isFinite(lastMs) || byDriver.size === 0) {
      return [];
    }

    for (const stream of byDriver.values()) {
      stream.sort((a, b) => a.timestampMs - b.timestampMs);
    }

    const frames: HistoryPlaybackFrame[] = [];
    for (let tickMs = firstMs; tickMs <= lastMs; tickMs += HISTORY_STEP_DURATION_MS) {
      const frameEvents: HistoryReplayEventPayload[] = [];
      for (const stream of byDriver.values()) {
        const interpolated = this.interpolateDriverEventAt(stream, tickMs);
        if (interpolated) {
          frameEvents.push(interpolated);
        }
      }
      frameEvents.sort((a, b) => a.driver_number - b.driver_number);
      if (frameEvents.length) {
        frames.push({
          timestamp: new Date(tickMs).toISOString(),
          events: frameEvents,
        });
      }
    }

    const hasLastTick = frames.length > 0
      && Date.parse(frames[frames.length - 1].timestamp ?? '') === lastMs;
    if (!hasLastTick) {
      const frameEvents: HistoryReplayEventPayload[] = [];
      for (const stream of byDriver.values()) {
        const interpolated = this.interpolateDriverEventAt(stream, lastMs);
        if (interpolated) {
          frameEvents.push(interpolated);
        }
      }
      frameEvents.sort((a, b) => a.driver_number - b.driver_number);
      if (frameEvents.length) {
        frames.push({
          timestamp: new Date(lastMs).toISOString(),
          events: frameEvents,
        });
      }
    }

    return frames;
  }

  private interpolateDriverEventAt(
    stream: DriverTimedEvent[],
    tickMs: number,
  ): HistoryReplayEventPayload | null {
    if (!stream.length) {
      return null;
    }

    if (tickMs <= stream[0].timestampMs) {
      const first = stream[0].event;
      return {
        ...first,
        date: new Date(tickMs).toISOString(),
      };
    }

    const lastIndex = stream.length - 1;
    if (tickMs >= stream[lastIndex].timestampMs) {
      const last = stream[lastIndex].event;
      return {
        ...last,
        date: new Date(tickMs).toISOString(),
      };
    }

    let low = 0;
    let high = lastIndex;
    while (low + 1 < high) {
      const mid = Math.floor((low + high) / 2);
      if (stream[mid].timestampMs <= tickMs) {
        low = mid;
      } else {
        high = mid;
      }
    }

    const before = stream[low];
    const after = stream[high];
    const span = Math.max(1, after.timestampMs - before.timestampMs);
    const ratio = Math.max(0, Math.min(1, (tickMs - before.timestampMs) / span));

    const beforeEvent = before.event;
    const afterEvent = after.event;
    return {
      ...beforeEvent,
      date: new Date(tickMs).toISOString(),
      x: beforeEvent.x + (afterEvent.x - beforeEvent.x) * ratio,
      y: beforeEvent.y + (afterEvent.y - beforeEvent.y) * ratio,
      z: beforeEvent.z + (afterEvent.z - beforeEvent.z) * ratio,
      lap_number: ratio < 0.5 ? beforeEvent.lap_number : afterEvent.lap_number,
      position: ratio < 0.5 ? beforeEvent.position : afterEvent.position,
      position_date: ratio < 0.5 ? beforeEvent.position_date : afterEvent.position_date,
    };
  }

  private playbackStepDelayMs(): number {
    const speed = Math.max(1, this.playbackSpeed());
    const scaled = Math.round(HISTORY_STEP_DURATION_MS / speed);
    return Math.max(HISTORY_MIN_STEP_DURATION_MS, scaled);
  }

  private currentRenderedPoint(driver: DriverPayload, nowMs: number): TrackPoint | null {
    const number = driver.driver_number;
    if (typeof number !== 'number') {
      if (driver.track_point && this.isTrackPoint(driver.track_point)) {
        return { x: driver.track_point.x, y: driver.track_point.y, z: driver.track_point.z };
      }
      return null;
    }

    const animation = this.driverAnimationByNumber.get(number);
    if (!animation) {
      if (driver.track_point && this.isTrackPoint(driver.track_point)) {
        return { x: driver.track_point.x, y: driver.track_point.y, z: driver.track_point.z };
      }
      return null;
    }

    const duration = Math.max(1, animation.durationMs);
    const progress = Math.max(0, Math.min(1, (nowMs - animation.startedAtMs) / duration));
    if (progress >= 1) {
      this.driverAnimationByNumber.delete(number);
      return { x: animation.to.x, y: animation.to.y, z: animation.to.z };
    }

    return {
      x: animation.from.x + (animation.to.x - animation.from.x) * progress,
      y: animation.from.y + (animation.to.y - animation.from.y) * progress,
      z: animation.from.z + (animation.to.z - animation.from.z) * progress,
    };
  }

  private buildYearOptions(): number[] {
    const currentYear = new Date().getFullYear();
    const years: number[] = [];
    for (let year = currentYear; year >= currentYear - 10; year -= 1) {
      years.push(year);
    }
    return years;
  }

  private safeTime(value: string | null | undefined): string {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleTimeString('de-DE');
  }

  private safeDateTime(value: string | null | undefined): string {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleString('de-DE');
  }

  private requestTrackRender(): void {
    if (this.trackRenderQueued) {
      return;
    }
    this.trackRenderQueued = true;
    requestAnimationFrame(() => {
      this.trackRenderQueued = false;
      this.renderTrackCanvas();
    });
  }

  private requestTrackRenderBurst(): void {
    this.requestTrackRender();
    window.setTimeout(() => this.requestTrackRender(), 80);
    window.setTimeout(() => this.requestTrackRender(), 220);
  }

  private async getOrLoadLapPayload(
    sessionKey: number,
    lapNumber: number,
    generation: number,
  ): Promise<HistoryReplayLapPayload> {
    const cached = this.lapCache.get(lapNumber);
    if (cached) {
      return cached;
    }

    const inFlight = this.lapLoadPromises.get(lapNumber);
    if (inFlight) {
      return inFlight;
    }

    const request = firstValueFrom(this.api.getHistoryReplayLap(sessionKey, lapNumber, HISTORY_SAMPLE_STEP))
      .then((payload) => {
        if (generation === this.prefetchGeneration) {
          this.lapCache.set(lapNumber, payload);
        }
        return payload;
      })
      .finally(() => {
        this.lapLoadPromises.delete(lapNumber);
      });

    this.lapLoadPromises.set(lapNumber, request);
    return request;
  }

  private prefetchUpcomingLaps(currentLap: number, generation: number): void {
    if (generation !== this.prefetchGeneration) {
      return;
    }
    const sessionKey = this.selectedSessionKey();
    if (!sessionKey) {
      return;
    }
    const laps = this.lapNumbers();
    const currentIndex = laps.indexOf(currentLap);
    if (currentIndex === -1) {
      return;
    }
    const nextLaps = laps.slice(currentIndex + 1, currentIndex + 2);
    for (const lap of nextLaps) {
      void this.getOrLoadLapPayload(sessionKey, lap, generation).catch(() => undefined);
    }
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
    const drivers = this.drivers();
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
    const projector = this.projector(bounds, rect.width, rect.height);

    context.lineJoin = 'round';
    context.lineCap = 'round';

    context.beginPath();
    const firstPoint = projector(points[0]);
    context.moveTo(firstPoint.x, firstPoint.y);
    for (let index = 1; index < points.length; index += 1) {
      const point = projector(points[index]);
      context.lineTo(point.x, point.y);
    }
    context.strokeStyle = 'rgba(255, 36, 56, 0.2)';
    context.lineWidth = 18;
    context.stroke();

    context.beginPath();
    context.moveTo(firstPoint.x, firstPoint.y);
    for (let index = 1; index < points.length; index += 1) {
      const point = projector(points[index]);
      context.lineTo(point.x, point.y);
    }
    context.strokeStyle = '#3f4554';
    context.lineWidth = 10;
    context.stroke();

    context.beginPath();
    context.moveTo(firstPoint.x, firstPoint.y);
    for (let index = 1; index < points.length; index += 1) {
      const point = projector(points[index]);
      context.lineTo(point.x, point.y);
    }
    context.strokeStyle = 'rgba(171, 181, 199, 0.6)';
    context.lineWidth = 1.5;
    context.stroke();

    this._stackByCell.clear();
    const nowMs = performance.now();
    let hasActiveAnimations = false;
    for (const driver of drivers) {
      const marker = this.currentRenderedPoint(driver, nowMs);
      if (!marker || !this.isTrackPoint(marker)) continue;
      const driverNumber = driver.driver_number;
      if (typeof driverNumber === 'number' && this.driverAnimationByNumber.has(driverNumber)) {
        hasActiveAnimations = true;
      }
      const projected = projector(marker);
      const point = this.disperseProjectedPoint(projected);
      const color = this.driverColor(driver);
      const label = driver.name_acronym ?? String(driver.driver_number ?? '?');

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
    }

    if (hasActiveAnimations) {
      this.requestTrackRender();
    }
  }

  private disperseProjectedPoint(point: { x: number; y: number }): { x: number; y: number } {
    const cellSize = 10;
    const cellX = Math.round(point.x / cellSize);
    const cellY = Math.round(point.y / cellSize);
    const key = `${cellX}:${cellY}`;
    if (!this._stackByCell.has(key)) {
      this._stackByCell.set(key, 0);
      return point;
    }
    const stackIndex = (this._stackByCell.get(key) ?? 0) + 1;
    this._stackByCell.set(key, stackIndex);
    const angle = stackIndex * 2.399963229728653;
    const radius = Math.min(14, 3 + stackIndex * 2);
    return {
      x: point.x + Math.cos(angle) * radius,
      y: point.y + Math.sin(angle) * radius,
    };
  }

  private _stackByCell = new Map<string, number>();

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
  ): (point: TrackPoint) => { x: number; y: number } {
    const padding = 20;
    const spanX = Math.max(1, bounds.maxX - bounds.minX);
    const spanY = Math.max(1, bounds.maxY - bounds.minY);
    const fitScale = Math.min((width - 2 * padding) / spanX, (height - 2 * padding) / spanY);
    const scale = fitScale * 0.95;
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
      return '#dbe4fb';
    }
    return `#${raw.replace('#', '')}`;
  }

  private toErrorMessage(error: unknown): string {
    if (typeof error === 'string') return error;
    if (error instanceof Error && error.message) return error.message;
    if (typeof error === 'object' && error !== null && 'message' in error) {
      const message = (error as { message?: unknown }).message;
      if (typeof message === 'string' && message) return message;
    }
    return 'Unbekannter Fehler';
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
}
