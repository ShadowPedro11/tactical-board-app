import { Component, ElementRef, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Team, TeamService } from './team.service';
import { formations } from './formations';
import { teamUniforms, Uniform } from './uniforms';

interface PlayerToken {
  id: number;
  team: 'A' | 'B';
  // Positions stored as percentages (0 to 100) relative to the field dimensions.
  x: number;
  y: number;
  number?: string;
  name?: string;
}

interface Formation {
  name: string;
  // Positions in pixels relative to a fixed 850x550 field.
  positions: { x: number; y: number }[];
}

@Component({
  selector: 'app-tactis-board',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './tactis-board.component.html',
  styleUrls: ['./tactis-board.component.css']
})
export class TactisBoardComponent implements OnInit {
  @ViewChild('container', { static: true }) container!: ElementRef<HTMLElement>;

  teamUniforms = teamUniforms;
  formations = formations;
  teams: Team[] = [];
  // Separate selected teams for left (A) and right (B)
  selectedTeamA: Team | null = null;
  selectedTeamB: Team | null = null;

  // New: Uniform selections for each team side.
  // For each team we store the selected Uniform (if any).
  selectedUniformA: Uniform | null = null;
  selectedUniformB: Uniform | null = null;

  selectedFormationA: Formation | null = null;
  selectedFormationB: Formation | null = null;

  teamATokens: PlayerToken[] = [];
  teamBTokens: PlayerToken[] = [];

  // For drag-and-drop (only in free layout)
  draggingToken: PlayerToken | null = null;
  dragOffsetX: number = 0;
  dragOffsetY: number = 0;

  // For token layout – assume "free" is the default.
  tokenLayout: 'free' | 'vertical' | 'horizontal' = 'free';

  constructor(private teamService: TeamService) {}

  ngOnInit(): void {
    // Load teams from your local Portugal.json via TeamService.
    this.teamService.getTeams().subscribe({
      next: (data) => (this.teams = data),
      error: (err) => console.error('Error fetching teams:', err)
    });
  }

  // Called when a formation is selected.
  selectFormation(team: 'A' | 'B', formationIndex: number): void {
    const formation = this.formations[formationIndex];
    if (team === 'A') {
      this.selectedFormationA = formation;
      this.teamATokens = formation.positions.map((pos, index) => ({
        id: index,
        team: 'A',
        x: (pos.x / 850) * 100,
        y: (pos.y / 550) * 100,
        number: '',
        name: ''
      }));
    } else {
      this.selectedFormationB = formation;
      this.teamBTokens = formation.positions.map((pos, index) => ({
        id: index,
        team: 'B',
        x: 95.5 - ((pos.x / 850) * 100),
        y: (pos.y / 550) * 100,
        number: '',
        name: ''
      }));
    }
  }

  // Updated team selection: include a side parameter ("A" for left, "B" for right).
  onTeamSelect(side: 'A' | 'B', event: any): void {
    const teamId = +event.target.value;
    const selected = this.teams.find(team => team.team.id === teamId) || null;
    if (side === 'A') {
      this.selectedTeamA = selected;
      // Set default uniform (if available) for Team A.
      if (selected && teamUniforms[selected.team.id]) {
        this.selectedUniformA = teamUniforms[selected.team.id].find(u => u.name === 'Home') || teamUniforms[selected.team.id][0];
      }
      console.log('Selected Team A:', this.selectedTeamA, this.selectedUniformA);
    } else {
      this.selectedTeamB = selected;
      // Set default uniform (if available) for Team B.
      if (selected && teamUniforms[selected.team.id]) {
        this.selectedUniformB = teamUniforms[selected.team.id].find(u => u.name === 'Home') || teamUniforms[selected.team.id][0];
      }
      console.log('Selected Team B:', this.selectedTeamB, this.selectedUniformB);
    }
  }

  // New method: Change uniform for a given team side.
  onUniformSelect(side: 'A' | 'B', uniformId: number): void {
    if (side === 'A' && this.selectedTeamA) {
      const uniforms = teamUniforms[this.selectedTeamA.team.id];
      this.selectedUniformA = uniforms.find(u => u.id === uniformId) || null;
      console.log('Team A uniform changed to:', this.selectedUniformA);
    } else if (side === 'B' && this.selectedTeamB) {
      const uniforms = teamUniforms[this.selectedTeamB.team.id];
      this.selectedUniformB = uniforms.find(u => u.id === uniformId) || null;
      console.log('Team B uniform changed to:', this.selectedUniformB);
    }
  }

  // Helper method to get a token's background style.
  // For a "single" uniform type, simply return the single color.
  // For a "vertical" or "horizontal" type with 2+ colors, return a CSS gradient.
  getTokenBackground(token: PlayerToken): string {
    let uniform: Uniform | null = null;
    if (token.team === 'A' && this.selectedUniformA) {
      uniform = this.selectedUniformA;
    } else if (token.team === 'B' && this.selectedUniformB) {
      uniform = this.selectedUniformB;
    }
    if (!uniform) {
      // Fallback default colors.
      return token.team === 'A' ? 'rgba(255, 0, 0, 1)' : 'rgba(0, 0, 255, 1)';
    }
    if (uniform.type === 'single' || uniform.colors.length === 1) {
      return uniform.colors[0];
    } else if (uniform.type === 'vertical') {
      if (uniform.colors.length >= 2) {
        return `linear-gradient(90deg, 
          ${uniform.colors[0]} 0%, ${uniform.colors[0]} 20%, 
          ${uniform.colors[1]} 20%, ${uniform.colors[1]} 40%, 
          ${uniform.colors[0]} 40%, ${uniform.colors[0]} 60%, 
          ${uniform.colors[1]} 60%, ${uniform.colors[1]} 80%, 
          ${uniform.colors[0]} 80%, ${uniform.colors[0]} 100%)`;
      }
    } else if (uniform.type === 'horizontal') {
      // Create horizontal stripes.
      if (uniform.colors.length >= 2) {
        return `linear-gradient(0deg, ${uniform.colors[0]} 50%, ${uniform.colors[1]} 50%)`;
      }
    }
    return uniform.colors[0];
  }

  // ---------------------------
  // DRAG & DROP IMPLEMENTATION (free layout only)
  // ---------------------------
  onTokenMouseDown(token: PlayerToken, event: MouseEvent): void {
    if (this.tokenLayout !== 'free') return;
    if (event.button !== 0) return;
    event.stopPropagation();
    const containerRect = this.container.nativeElement.getBoundingClientRect();
    const tokenPixelX = (token.x / 100) * containerRect.width;
    const tokenPixelY = (token.y / 100) * containerRect.height;
    this.dragOffsetX = event.clientX - (containerRect.left + tokenPixelX);
    this.dragOffsetY = event.clientY - (containerRect.top + tokenPixelY);
    this.draggingToken = token;
  }

  onFieldMouseMove(event: MouseEvent): void {
    if (this.tokenLayout !== 'free') return;
    if (!this.draggingToken) return;
    const containerRect = this.container.nativeElement.getBoundingClientRect();
    const newPixelX = event.clientX - containerRect.left - this.dragOffsetX;
    const newPixelY = event.clientY - containerRect.top - this.dragOffsetY;
    this.draggingToken.x = (newPixelX / containerRect.width) * 100;
    this.draggingToken.y = (newPixelY / containerRect.height) * 100;
  }

  onFieldMouseUp(event: MouseEvent): void {
    if (this.tokenLayout !== 'free') return;
    this.draggingToken = null;
  }
  // ---------------------------
  // END DRAG & DROP IMPLEMENTATION
  // ---------------------------

  onFieldClick(event: MouseEvent): void {
    if (this.draggingToken) return;
  }

  onTokenRightClick(token: PlayerToken, event: MouseEvent): void {
    event.preventDefault();
    event.stopPropagation();
    const newNumber = prompt("Enter player's number:", token.number || '');
    if (newNumber !== null) {
      token.number = newNumber;
    }
    const newName = prompt("Enter player's name:", token.name || '');
    if (newName !== null) {
      token.name = newName;
    }
  }
}
