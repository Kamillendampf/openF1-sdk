import { Routes } from '@angular/router';
import { HistoryViewComponent } from './views/history-view/history-view';
import { LiveViewComponent } from './views/live-view/live-view';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'live' },
  { path: 'live', component: LiveViewComponent },
  { path: 'history', component: HistoryViewComponent },
  { path: '**', redirectTo: 'live' },
];
