import { Routes } from '@angular/router';
import { DashboardComponent } from './dashboard/dashboard.component';
import { TactisBoardComponent } from './tactis-board/tactis-board.component';
import { LiveTactisBoardComponent } from './live-tactis-board/live-tactis-board.component';

export const routes: Routes = [
    { path: '', redirectTo: 'tactis-board', pathMatch: 'full' },
    { path: 'tactis-board', component: TactisBoardComponent },
    { path: 'live-tactis-board', component: LiveTactisBoardComponent },
    { path: 'settings', component: DashboardComponent },


];
