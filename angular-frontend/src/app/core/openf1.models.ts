export interface TrackPoint {
  x: number;
  y: number;
  z: number;
}

export interface DriverTrackPoint extends TrackPoint {
  date?: string | null;
}

export interface LapPayload {
  current: number | null;
  max: number | null;
  display: string | null;
}

export interface DriverPayload {
  driver_number?: number;
  name_acronym?: string;
  full_name?: string;
  first_name?: string;
  last_name?: string;
  headshot_url?: string | null;
  team_name?: string;
  team_colour?: string;
  current_position?: number | null;
  current_lap?: number | null;
  position_date?: string | null;
  lap_date?: string | null;
  track_point?: DriverTrackPoint | null;
}

export interface RunPayload {
  mode: string;
  session_key: number | string;
  session_name: string;
  session_type: string;
  points: TrackPoint[];
  circuit_name: string;
  drivers: DriverPayload[];
  lap: LapPayload;
}

export interface LivePayload {
  mode: string;
  session_key: number | string;
  session_name: string;
  session_type: string;
  circuit_name: string;
  session_started_at?: string | null;
  track: TrackPoint[];
  drivers: DriverPayload[];
  lap: LapPayload;
  position_timestamp?: string | null;
  generated_at?: string | null;
}

export interface WeatherRowPayload {
  date: string | null;
  air_temperature: number | null;
  track_temperature: number | null;
  humidity: number | null;
  pressure: number | null;
  wind_speed: number | null;
  wind_direction: number | null;
  rainfall: number | null;
  condition: 'clear' | 'cloudy' | 'rain' | 'hot' | string;
  icon: string;
}

export interface WeatherInsightsPayload {
  session_key: number | string;
  meeting_key: number | string;
  session_name: string;
  session_type: string;
  circuit_name: string;
  latest: WeatherRowPayload;
  history: WeatherRowPayload[];
  generated_at: string;
}

export interface TeamRadioEventPayload {
  date: string;
  driver_number: number;
  driver_name: string | null;
  team_name: string | null;
  team_colour: string | null;
  recording_url: string;
}

export interface TeamRadioInsightsPayload {
  session_key: number | string;
  meeting_key: number | string;
  session_name: string;
  session_type: string;
  circuit_name: string;
  events: TeamRadioEventPayload[];
  count: number;
  generated_at: string;
}

export interface HistorySessionSummary {
  session_key: number;
  meeting_key: number;
  year: number;
  session_name: string;
  session_type: string;
  circuit_name: string;
  country_name: string;
  location: string;
  date_start: string | null;
}

export interface HistorySessionsPayload {
  sessions: HistorySessionSummary[];
}

export interface HistoryReplayEventPayload {
  date: string;
  driver_number: number;
  x: number;
  y: number;
  z: number;
  lap_number: number;
  position?: number | null;
  position_date?: string | null;
}

export interface HistoryReplayInitPayload {
  mode: string;
  session_key: number | string;
  meeting_key: number | string;
  session_name: string;
  session_type: string;
  circuit_name: string;
  date_start: string | null;
  track: TrackPoint[];
  drivers: DriverPayload[];
  lap: LapPayload;
  replay: {
    lap_numbers: number[];
    first_lap: number;
    last_lap: number;
  };
  generated_at: string;
}

export interface HistoryReplayLapPayload {
  mode: string;
  session_key: number | string;
  lap: LapPayload;
  playback: {
    lap_number: number;
    sample_step: number;
    event_count: number;
    started_at: string | null;
    ended_at: string | null;
    events: HistoryReplayEventPayload[];
  };
  generated_at: string;
}
