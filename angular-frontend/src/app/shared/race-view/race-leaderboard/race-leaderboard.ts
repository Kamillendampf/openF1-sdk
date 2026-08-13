import { CommonModule } from '@angular/common';
import { Component, input, output } from '@angular/core';

import { DriverPayload } from '../../../core/openf1.models';

@Component({
  selector: 'app-race-leaderboard',
  imports: [CommonModule],
  templateUrl: './race-leaderboard.html',
  styleUrl: './race-leaderboard.scss',
})
export class RaceLeaderboardComponent {
  readonly title = input('Positionen');
  readonly drivers = input<DriverPayload[]>([]);
  readonly emptyText = input('Keine Positionsdaten vorhanden.');
  readonly interactive = input(false);
  readonly activeDriverNumbers = input<number[]>([]);
  readonly soloDriverNumber = input<number | null>(null);

  readonly driverSelected = output<number>();

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

  isRadioActive(driverNumber: number | null | undefined): boolean {
    return typeof driverNumber === 'number' && this.activeDriverNumbers().includes(driverNumber);
  }

  isSolo(driverNumber: number | null | undefined): boolean {
    return typeof driverNumber === 'number' && this.soloDriverNumber() === driverNumber;
  }

  isRadioHighlighted(driverNumber: number | null | undefined): boolean {
    return this.isRadioActive(driverNumber) || this.isSolo(driverNumber);
  }

  selectDriver(driverNumber: number | null | undefined): void {
    if (!this.interactive() || typeof driverNumber !== 'number') {
      return;
    }
    this.driverSelected.emit(driverNumber);
  }

  selectDriverFromSpace(event: Event, driverNumber: number | null | undefined): void {
    if (!this.interactive()) {
      return;
    }
    event.preventDefault();
    this.selectDriver(driverNumber);
  }
}
