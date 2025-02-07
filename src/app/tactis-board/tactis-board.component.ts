import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { formations } from './formations';

interface PlayerToken {
  id: number;
  team: 'A' | 'B';
  x: number;
  y: number;
  number?: string;
  name?: string;
}


interface Formation {
  name: string;
  // positions in pixels relative to a fixed 850x550 field
  positions: { x: number; y: number }[];
}

@Component({
  selector: 'app-tactis-board',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './tactis-board.component.html',
  styleUrl: './tactis-board.component.css'
})
export class TactisBoardComponent {
  formations = formations;

  selectedFormationA: Formation | null = null;
  selectedFormationB: Formation | null = null;

  teamATokens: PlayerToken[] = [];
  teamBTokens: PlayerToken[] = [];

  movingToken: PlayerToken | null = null;

  // When a formation is selected, convert fixed positions to percentages.
  selectFormation(team: 'A' | 'B', formationIndex: number): void {
    const formation = this.formations[formationIndex];
    if (team === 'A') {
      this.selectedFormationA = formation;
      this.teamATokens = formation.positions.map((pos, index) => ({
        id: index,
        team: 'A',
        x: (pos.x / 850) * 100, // convert to percentage
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

  // On field click, if a token is selected for moving, update its position (in percentages).
  onFieldClick(event: MouseEvent): void {
    if (this.movingToken) {
      const field = event.currentTarget as HTMLElement;
      const rect = field.getBoundingClientRect();
      const clickX = event.clientX - rect.left;
      const clickY = event.clientY - rect.top;
      // Convert the click position into percentages of the current field size.
      const leftPercent = (clickX / rect.width) * 100;
      const topPercent = (clickY / rect.height) * 100;
      this.movingToken.x = leftPercent;
      this.movingToken.y = topPercent;
      this.movingToken = null;
    }
  }

  // Left-click on a token to select it for moving.
  onTokenLeftClick(token: PlayerToken, event: MouseEvent): void {
    event.stopPropagation(); // Prevent field click from firing
    this.movingToken = token;
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
