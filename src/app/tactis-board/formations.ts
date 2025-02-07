interface Formation {
    name: string;
    // positions in pixels relative to a fixed 850x550 field
    positions: { x: number; y: number }[];
}

export const formations: Formation[] = [
    {
        name: '---',
        positions: []
    },
    {
      name: '4-4-2',
      positions: [
        { x: 0, y: 240 }, // Goalkeeper
        { x: 100, y: 450 }, // Right Back
        { x: 100, y: 305 }, // Right Center Back
        { x: 100, y: 170 }, // Left Center Back
        { x: 100, y: 60 }, // Left Back
        { x: 250, y: 450 }, // Right Midfielder
        { x: 235, y: 300 }, // Right Center Midfielder
        { x: 235, y: 187 }, // Left Center Midfielder
        { x: 250, y: 60 }, // Left Midfielder
        { x: 350, y: 320 }, // Right Forward
        { x: 350, y: 150 }  // Left Forward
      ]
    },
    {
      name: '4-3-3',
      positions: [
        { x: 0, y: 240 }, // Goalkeeper
        { x: 100, y: 450 }, // Right Back
        { x: 100, y: 305 }, // Right Center Back
        { x: 100, y: 170 }, // Left Center Back
        { x: 100, y: 60 }, // Left Back
        { x: 235, y: 370 }, // Right Midfielder
        { x: 205, y: 240 }, // Center Midfielder
        { x: 235, y: 100 }, // Left Midfielder
        { x: 350, y: 450 }, // Right Forward
        { x: 350, y: 240 }, // Center Forward
        { x: 350, y: 60 }  // Left Forward
      ]
    }
  ];