import { Component, ElementRef, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Team, TeamService } from './team.service';
import { formations } from './formations';

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
  // Reference to the field container (make sure your HTML container has #container)
  @ViewChild('container', { static: true }) container!: ElementRef<HTMLElement>;

  formations = formations;
  teams: Team[] = [];
  selectedTeam: Team | null = null;

  selectedFormationA: Formation | null = null;
  selectedFormationB: Formation | null = null;

  teamATokens: PlayerToken[] = [];
  teamBTokens: PlayerToken[] = [];

  // For drag-and-drop:
  draggingToken: PlayerToken | null = null;
  dragOffsetX: number = 0;
  dragOffsetY: number = 0;

  constructor(private teamService: TeamService) {}

  ngOnInit(): void {
    // Fetch teams from the external API
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

  // Handle team selection from a dropdown.
  onTeamSelect(event: any): void {
    const teamId = +event.target.value;
    this.selectedTeam = this.teams.find(team => team.id === teamId) || null;
    console.log('Selected team:', this.selectedTeam);
  }

  // ---------------------------
  // DRAG & DROP IMPLEMENTATION
  // ---------------------------

  // Called when a token is pressed (left mouse button) to start dragging.
  onTokenMouseDown(token: PlayerToken, event: MouseEvent): void {
    if (event.button !== 0) return; // Only react to left-button
    event.stopPropagation();
    // Get the container's bounding rectangle.
    const containerRect = this.container.nativeElement.getBoundingClientRect();
    // Calculate token's current pixel position based on its percentage.
    const tokenPixelX = (token.x / 100) * containerRect.width;
    const tokenPixelY = (token.y / 100) * containerRect.height;
    // Calculate the offset from the mouse position to the token's top-left corner.
    this.dragOffsetX = event.clientX - (containerRect.left + tokenPixelX);
    this.dragOffsetY = event.clientY - (containerRect.top + tokenPixelY);
    this.draggingToken = token;
  }

  // Called as the mouse moves over the field container.
  onFieldMouseMove(event: MouseEvent): void {
    if (!this.draggingToken) return;
    const containerRect = this.container.nativeElement.getBoundingClientRect();
    // Calculate new pixel coordinates for the token's top-left corner.
    const newPixelX = event.clientX - containerRect.left - this.dragOffsetX;
    const newPixelY = event.clientY - containerRect.top - this.dragOffsetY;
    // Update token position in percentages.
    this.draggingToken.x = (newPixelX / containerRect.width) * 100;
    this.draggingToken.y = (newPixelY / containerRect.height) * 100;
  }

  // Called on mouseup or when the mouse leaves the container to end dragging.
  onFieldMouseUp(event: MouseEvent): void {
    this.draggingToken = null;
  }

  // ---------------------------
  // END DRAG & DROP IMPLEMENTATION
  // ---------------------------

  // (Optional) If the user clicks on the field and a token is selected, update its position.
  onFieldClick(event: MouseEvent): void {
    if (this.draggingToken) return; // Ignore if dragging is in progress.
    const field = event.currentTarget as HTMLElement;
    const rect = field.getBoundingClientRect();
    const clickX = event.clientX - rect.left;
    const clickY = event.clientY - rect.top;
    // (Optional) Update the token position if desired.
  }

  // Right-click on a token to edit its number and name.
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
