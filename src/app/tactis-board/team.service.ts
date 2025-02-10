import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Team {
  id: number;
  name: string;
  logoUrl?: string;
}

@Injectable({
  providedIn: 'root'
})

export class TeamService {
  // Replace with your actual API endpoint.
  private apiUrl = 'https://api.example.com/teams';

  constructor(private http: HttpClient) {}

  getTeams(): Observable<Team[]> {
    const mockTeams: Team[] = [
      { id: 1, name: 'Team A', logoUrl: 'https://example.com/logoA.png' },
      { id: 2, name: 'Team B', logoUrl: 'https://example.com/logoB.png' },
      { id: 3, name: 'Team C', logoUrl: 'https://example.com/logoC.png' }
    ];
    return new Observable<Team[]>(observer => {
      observer.next(mockTeams);
      observer.complete();
    });
    
  }
}
