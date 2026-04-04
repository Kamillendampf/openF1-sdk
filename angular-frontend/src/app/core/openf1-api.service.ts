import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import {
  HistoryReplayInitPayload,
  HistoryReplayLapPayload,
  HistorySessionsPayload,
  LivePayload,
  RunPayload,
  TeamRadioInsightsPayload,
  WeatherInsightsPayload,
} from './openf1.models';

const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';

@Injectable({ providedIn: 'root' })
export class OpenF1ApiService {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = this.resolveApiBaseUrl();

  getBootstrap(): Observable<RunPayload> {
    return this.http.get<RunPayload>(this.apiUrl('/api/run'));
  }

  getLive(): Observable<LivePayload> {
    return this.http.get<LivePayload>(this.apiUrl('/api/live'));
  }

  getWeather(): Observable<WeatherInsightsPayload> {
    return this.http.get<WeatherInsightsPayload>(this.apiUrl('/api/insights/weather'));
  }

  getTeamRadio(limit = 30): Observable<TeamRadioInsightsPayload> {
    return this.http.get<TeamRadioInsightsPayload>(this.apiUrl(`/api/insights/team-radio?limit=${limit}`));
  }

  getHistorySessions(year?: number, limit = 120): Observable<HistorySessionsPayload> {
    let params = new HttpParams().set('limit', limit);
    if (typeof year === 'number') {
      params = params.set('year', year);
    }
    return this.http.get<HistorySessionsPayload>(this.apiUrl('/api/history/sessions'), { params });
  }

  getHistoryReplayInit(sessionKey: number): Observable<HistoryReplayInitPayload> {
    const params = new HttpParams().set('session_key', sessionKey);
    return this.http.get<HistoryReplayInitPayload>(this.apiUrl('/api/history/replay/init'), { params });
  }

  getHistoryReplayLap(sessionKey: number, lapNumber: number, sampleStep = 1): Observable<HistoryReplayLapPayload> {
    const params = new HttpParams()
      .set('session_key', sessionKey)
      .set('lap_number', lapNumber)
      .set('sample_step', sampleStep);
    return this.http.get<HistoryReplayLapPayload>(this.apiUrl('/api/history/replay/lap'), { params });
  }

  private apiUrl(path: string): string {
    return `${this.apiBaseUrl}${path}`;
  }

  private resolveApiBaseUrl(): string {
    const runtimeConfig = globalThis as { __OPENF1_API_BASE__?: unknown };
    const configured = runtimeConfig.__OPENF1_API_BASE__;
    if (typeof configured === 'string' && configured.trim()) {
      return configured.replace(/\/+$/, '');
    }
    return DEFAULT_API_BASE_URL;
  }
}
