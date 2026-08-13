import { CommonModule } from '@angular/common';
import { Component, input } from '@angular/core';

import { WeatherInsightsPayload } from '../../../core/openf1.models';

@Component({
  selector: 'app-weather-card',
  imports: [CommonModule],
  templateUrl: './weather-card.html',
  styleUrl: './weather-card.scss',
})
export class WeatherCardComponent {
  readonly weather = input<WeatherInsightsPayload | null>(null);

  visualClass(): string {
    const condition = this.weather()?.latest?.condition;
    if (condition === 'rain') return 'is-rain';
    if (condition === 'cloudy') return 'is-cloudy';
    return 'is-clear';
  }

  conditionLabel(): string {
    const condition = this.weather()?.latest?.condition;
    if (condition === 'rain') return 'Regen';
    if (condition === 'cloudy') return 'Bewoelkt';
    if (condition === 'hot') return 'Heiss';
    if (condition === 'clear') return 'Klar';
    return 'Wetter';
  }

  formatWeatherValue(value: number | null | undefined, suffix = '', digits = 1): string {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      return '-';
    }
    const rounded = value.toFixed(digits).replace(/\.0$/, '');
    return suffix ? `${rounded} ${suffix}` : rounded;
  }

  windDirectionStyle(value: number | null | undefined): { transform: string } {
    const degrees = typeof value === 'number' && Number.isFinite(value) ? value : 0;
    return { transform: `rotate(${degrees}deg)` };
  }
}
