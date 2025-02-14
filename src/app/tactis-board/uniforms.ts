// uniforms.ts

export interface Uniform {
    id: number;
    name: string;
    colors: string[];
    type: 'single' | 'vertical' | 'horizontal';
  }
  
  export const teamUniforms: { [id: number]: Uniform[] } = {
    211: [ // Benfica
      { id: 1, name: 'Home', colors: ['#f5413c'], type: 'single' },
      { id: 2, name: 'Away', colors: ['#23252a'], type: 'single' },
      { id: 3, name: 'Third', colors: ['#c3c8cc'], type: 'single' }
    ],
    212: [ // FC Porto
      { id: 1, name: 'Home', colors: [ '#e7e6eb', '#024293'], type: 'vertical' },
      { id: 2, name: 'Away', colors: ['#fc9f01'], type: 'single' },
      { id: 3, name: 'Third', colors: ['#00529F'], type: 'single' },
    ],
    215: [ // Moreirense
      //{ id: 1, name: 'Home', colors: ['#FF5A00'], type: 'single' },
      //{ id: 2, name: 'Away', colors: ['#FFFFFF'], type: 'single' },
      //{ id: 3, name: 'Third', colors: ['#FF5A00', '#000000'], type: 'vertical' }
    ],
    225: [ // Nacional
      //{ id: 1, name: 'Home', colors: ['#8B0000'], type: 'single' },
      //{ id: 2, name: 'Away', colors: ['#FFFFFF'], type: 'single' },
      //{ id: 3, name: 'Third', colors: ['#8B0000', '#000000'], type: 'vertical' }
    ],
    217: [ // SC Braga
      //{ id: 1, name: 'Home', colors: ['#E60026'], type: 'single' },
      //{ id: 2, name: 'Away', colors: ['#FFFFFF'], type: 'single' },
      //{ id: 3, name: 'Third', colors: ['#E60026', '#FFFFFF'], type: 'vertical' }
    ],
    222: [ // Boavista
      //{ id: 1, name: 'Home', colors: ['#000000'], type: 'single' },
      //{ id: 2, name: 'Away', colors: ['#FFFFFF'], type: 'single' },
      //{ id: 3, name: 'Third', colors: ['#000000', '#808080'], type: 'vertical' }
    ],
    227: [ // Santa Clara
      //{ id: 1, name: 'Home', colors: ['#FFD700'], type: 'single' },
      //{ id: 2, name: 'Away', colors: ['#FFFFFF'], type: 'single' },
      //{ id: 3, name: 'Third', colors: ['#FFD700', '#000000'], type: 'vertical' }
    ],
    224: [ // Guimarães
      //{ id: 1, name: 'Home', colors: ['#008000'], type: 'single' },
      //{ id: 2, name: 'Away', colors: ['#FFFFFF'], type: 'single' },
      //{ id: 3, name: 'Third', colors: ['#008000', '#FFFFFF'], type: 'vertical' }
    ],
    226: [ // Rio Ave
      //{ id: 1, name: 'Home', colors: ['#0072BB'], type: 'single' },
      //{ id: 2, name: 'Away', colors: ['#FFFFFF'], type: 'single' },
      //{ id: 3, name: 'Third', colors: ['#0072BB', '#FFFFFF'], type: 'vertical' }
    ],
    228: [ // Sporting CP
      //{ id: 1, name: 'Home', colors: ['#008000'], type: 'single' },
      //{ id: 2, name: 'Away', colors: ['#FFFFFF'], type: 'single' },
      //{ id: 3, name: 'Third', colors: ['#008000', '#FF0000'], type: 'vertical' }
    ],
    230: [ // Estoril
      //{ id: 1, name: 'Home', colors: ['#FFA500'], type: 'single' },
      //{ id: 2, name: 'Away', colors: ['#FFFFFF'], type: 'single' },
      //{ id: 3, name: 'Third', colors: ['#FFA500', '#FFFFFF'], type: 'vertical' }
    ],
    231: [ // Farense
      //{ id: 1, name: 'Home', colors: ['#B22222'], type: 'single' },
      //{ id: 2, name: 'Away', colors: ['#FFFFFF'], type: 'single' },
      //{ id: 3, name: 'Third', colors: ['#B22222', '#FFFFFF'], type: 'vertical' }
    ],
    240: [ // Arouca
      //{ id: 1, name: 'Home', colors: ['#FFFF00'], type: 'single' },
      //{ id: 2, name: 'Away', colors: ['#FFFFFF'], type: 'single' },
      //{ id: 3, name: 'Third', colors: ['#FFFF00', '#000000'], type: 'vertical' }
    ],
    242: [ // Famalicão
      //{ id: 1, name: 'Home', colors: ['#1E90FF'], type: 'single' },
      //{ id: 2, name: 'Away', colors: ['#FFFFFF'], type: 'single' },
      //{ id: 3, name: 'Third', colors: ['#1E90FF', '#FFFFFF'], type: 'vertical' }
    ],
    762: [ // GIL Vicente
      //{ id: 1, name: 'Home', colors: ['#800080'], type: 'single' },
      //{ id: 2, name: 'Away', colors: ['#FFFFFF'], type: 'single' },
      //{ id: 3, name: 'Third', colors: ['#800080', '#FFFFFF'], type: 'vertical' }
    ],
    4716: [ // Casa Pia
      //{ id: 1, name: 'Home', colors: ['#4169E1'], type: 'single' },
      //{ id: 2, name: 'Away', colors: ['#FFFFFF'], type: 'single' },
      //{ id: 3, name: 'Third', colors: ['#4169E1', '#FFFFFF'], type: 'vertical' }
    ],
    15130: [ // Estrela
      //{ id: 1, name: 'Home', colors: ['#FFFFFF'], type: 'single' },
      //{ id: 2, name: 'Away', colors: ['#000000'], type: 'single' },
      //{ id: 3, name: 'Third', colors: ['#FFFFFF', '#000000'], type: 'vertical' }
    ],
    21595: [ // AVS
      //{ id: 1, name: 'Home', colors: ['#008080'], type: 'single' },
      //{ id: 2, name: 'Away', colors: ['#FFFFFF'], type: 'single' },
      //{ id: 3, name: 'Third', colors: ['#008080', '#FFFFFF'], type: 'vertical' }
    ]
  };  