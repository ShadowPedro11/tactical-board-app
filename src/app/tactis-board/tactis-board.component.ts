import { Component, ElementRef, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
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
  styleUrls: ['./tactis-board.component.css'] // Note the plural "styleUrls"
})
export class TactisBoardComponent {
  // Get a reference to the field container (make sure your template uses #container)
  @ViewChild('container', { static: true }) fieldContainer!: ElementRef<HTMLElement>;

  formations = formations;

  selectedFormationA: Formation | null = null;
  selectedFormationB: Formation | null = null;

  teamATokens: PlayerToken[] = [];
  teamBTokens: PlayerToken[] = [];

  // Properties for drag-and-drop
  draggingToken: PlayerToken | null = null;
  dragOffsetX: number = 0;
  dragOffsetY: number = 0;

  // When a formation is selected, convert the fixed pixel positions to percentages.
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
      // For Team B, mirror the positions (adjust the x coordinate).
      this.teamBTokens = formation.positions.map((pos, index) => ({
        id: index,
        team: 'B',
        x: 95.5 - ((pos.x / 850) * 100), // Adjusted mirror formula (modify as needed)
        y: (pos.y / 550) * 100,
        number: '',
        name: ''
      }));
    }
  }

  // Called when the user presses the left mouse button on a token.
  onTokenMouseDown(token: PlayerToken, event: MouseEvent): void {
    if (event.button !== 0) return; // Only proceed if it's the left button.
    event.stopPropagation();
    const containerRect = this.fieldContainer.nativeElement.getBoundingClientRect();
    // Calculate the token's current pixel position based on its percentage.
    const tokenPixelX = (token.x / 100) * containerRect.width;
    const tokenPixelY = (token.y / 100) * containerRect.height;
    // Record the offset between the mouse pointer and the token's top-left corner.
    this.dragOffsetX = event.clientX - (containerRect.left + tokenPixelX);
    this.dragOffsetY = event.clientY - (containerRect.top + tokenPixelY);
    this.draggingToken = token;
  }

  // Called on mousemove over the field container to update the token position.
  onFieldMouseMove(event: MouseEvent): void {
    if (!this.draggingToken) return;
    const containerRect = this.fieldContainer.nativeElement.getBoundingClientRect();
    const newPixelX = event.clientX - containerRect.left - this.dragOffsetX;
    const newPixelY = event.clientY - containerRect.top - this.dragOffsetY;
    // Update the token's position in percentages.
    this.draggingToken.x = (newPixelX / containerRect.width) * 100;
    this.draggingToken.y = (newPixelY / containerRect.height) * 100;
  }

  // Called on mouseup (or when leaving the container) to end dragging.
  onFieldMouseUp(event: MouseEvent): void {
    this.draggingToken = null;
  }

  // Right-click on a token to edit its number and name.
  onTokenRightClick(token: PlayerToken, event: MouseEvent): void {
    event.preventDefault(); // Prevent the context menu.
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