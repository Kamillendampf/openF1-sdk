import { Component, input } from '@angular/core';

import { CarDataInsightsPayload, DriverPayload } from '../../../core/openf1.models';

@Component({
  selector: 'app-vehicle-info-card',
  templateUrl: './vehicle-info-card.html',
  styleUrl: './vehicle-info-card.scss',
})
export class VehicleInfoCardComponent {
  readonly carData = input<CarDataInsightsPayload | null>(null);
  readonly driver = input<DriverPayload | null>(null);

  driverLabel(): string {
    const driver = this.driver();
    if (!driver) {
      const number = this.carData()?.driver_number;
      return typeof number === 'number' ? `Driver #${number}` : 'Fahrzeug';
    }
    return driver.name_acronym ?? driver.full_name ?? `#${driver.driver_number ?? '?'}`;
  }

  teamLabel(): string {
    return this.driver()?.team_name ?? 'Team n/a';
  }

  formatNumber(value: number | null | undefined, suffix = ''): string {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      return '-';
    }
    return suffix ? `${Math.round(value)} ${suffix}` : `${Math.round(value)}`;
  }

  formatPercent(value: number | null | undefined): string {
    return this.formatNumber(value, '%');
  }

  brakeLabel(value: number | null | undefined): string {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      return '-';
    }
    return value > 0 ? 'An' : 'Aus';
  }

  drsLabel(value: number | null | undefined): string {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      return '-';
    }
    return value > 0 ? `Mode ${value}` : 'Aus';
  }
}
