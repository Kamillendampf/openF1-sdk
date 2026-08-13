import { Component, input } from '@angular/core';

import { DriverPayload } from '../../../core/openf1.models';

@Component({
  selector: 'app-driver-grid',
  templateUrl: './driver-grid.html',
  styleUrl: './driver-grid.scss',
})
export class DriverGridComponent {
  readonly drivers = input<DriverPayload[]>([]);
  readonly title = input('Drivers');
  readonly emptyText = input('Keine Fahrerdaten vorhanden.');

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
}
