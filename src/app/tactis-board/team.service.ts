import { Injectable } from '@angular/core';
import { Observable, of } from 'rxjs';
import teamsData from '../json/Portugal.json'; // adjust the path as needed

export interface Team {
  team: {
    id: number;
    name: string;
    code: string | null;
    country: string;
    founded: number | null;
    national: boolean;
    logo: string;
  };
  venue: {
    id: number;
    name: string;
    address: string | null;
    city: string;
    capacity: number;
    surface: string;
    image: string;
  };
}

@Injectable({
  providedIn: 'root'
})
export class TeamService {
  getTeams(): Observable<Team[]> {
    return of(teamsData.response);
  }
}
