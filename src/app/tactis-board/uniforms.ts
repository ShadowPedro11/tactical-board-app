// uniforms.ts

export interface Uniform {
    id: number;
    name: string;
    colors: string[];
    type: 'single' | 'vertical' | 'horizontal' | 'dual';
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
      { id: 1, name: 'Home', colors: ['#0c714b', '#e6eae9'], type: 'vertical' },
      { id: 2, name: 'Away', colors: ['#034077'], type: 'single' },
      { id: 3, name: 'Third', colors: ['#008066'], type: 'single' }
    ],
    225: [ // Nacional
      { id: 1, name: 'Home', colors: ['#2a2a2a','#cecbca'], type: 'vertical' },
      { id: 2, name: 'Away', colors: ['#f8d118'], type: 'single' },
      { id: 3, name: 'Third', colors: ['#4b93ee'], type: 'single' }
    ],
    217: [ // SC Braga
      { id: 1, name: 'Home', colors: ['#ff1d2d'], type: 'single' },
      { id: 2, name: 'Away', colors: ['#343136'], type: 'single' },
      { id: 3, name: 'Third', colors: ['#ffe436'], type: 'single' }
    ],
    222: [ // Boavista
      { id: 1, name: 'Home', colors: ['#2a2a2a','#cecbca'], type: 'vertical' },
      { id: 2, name: 'Away', colors: ['#f06315'], type: 'single' },
      { id: 3, name: 'Third', colors: ['#2a2a2a', '#afafaf'], type: 'horizontal' }
    ],
    227: [ // Santa Clara
      { id: 1, name: 'Home', colors: ['#ff0000'], type: 'single' },
      { id: 2, name: 'Away', colors: ['#0036ac'], type: 'single' },
      { id: 3, name: 'Third', colors: ['#92c2d6'], type: 'single' }
    ],
    224: [ // Guimarães
      { id: 1, name: 'Home', colors: ['#e4e4e4'], type: 'single' },
      { id: 2, name: 'Away', colors: ['#303030'], type: 'single' },
      { id: 3, name: 'Third', colors: ['#ff4d0a'], type: 'single' }
    ],
    226: [ // Rio Ave
      { id: 1, name: 'Home', colors: ['#004847','#f3f4ee'], type: 'vertical' },
      { id: 2, name: 'Away', colors: ['#006b51'], type: 'single' },
      { id: 3, name: 'Third', colors: ['#30395e', '#00c8fb'], type: 'vertical' }
    ],
    228: [ // Sporting CP
      { id: 1, name: 'Home', colors: ['#313036','#00a06e','#e3e5ea'], type: 'horizontal' },
      { id: 2, name: 'Away', colors: ['#e6e7f1'], type: 'single' },
      { id: 3, name: 'Third', colors: ['#202129'], type: 'single' },
      { id: 4, name: 'Fourth', colors: ['#00f772'], type: 'single' }
    ],
    230: [ // Estoril
      { id: 1, name: 'Home', colors: ['#ffda45'], type: 'single' },
      { id: 2, name: 'Away', colors: ['#2d395e'], type: 'single' },
      { id: 3, name: 'Third', colors: ['#ff68a0'], type: 'single' }
    ],
    231: [ // Farense
      { id: 1, name: 'Home', colors: ['#e8edf1','#2a3437'], type: 'dual' },
      { id: 2, name: 'Away', colors: ['#f7f4f5'], type: 'single' },
      { id: 3, name: 'Third', colors: ['#6cc1a9'], type: 'single' }
    ],
    240: [ // Arouca
      { id: 1, name: 'Home', colors: ['#f4d532'], type: 'single' },
      { id: 2, name: 'Away', colors: ['#2e4160'], type: 'single' },
      { id: 3, name: 'Third', colors: ['#d4dde6'], type: 'single' }
    ],
    242: [ // Famalicão
      { id: 1, name: 'Home', colors: ['#fbfbfd'], type: 'single' },
      { id: 2, name: 'Away', colors: ['#364263'], type: 'single' },
      { id: 3, name: 'Third', colors: ['#ff681e', '#e9eeec'], type: 'vertical' }
    ],
    762: [ // GIL Vicente
      { id: 1, name: 'Home', colors: ['#a90916'], type: 'single' },
      { id: 2, name: 'Away', colors: ['#142974'], type: 'single' },
      { id: 3, name: 'Third', colors: ['#e8e8e8'], type: 'single' }
    ],
    4716: [ // Casa Pia
      { id: 1, name: 'Home', colors: ['#202020'], type: 'single' },
      { id: 2, name: 'Away', colors: ['#eeeeee'], type: 'single' },
      { id: 3, name: 'Third', colors: ['#ff0006', '#00a0d5'], type: 'horizontal' }
    ],
    15130: [ // Estrela
      { id: 1, name: 'Home', colors: ['#00645c', '#7c1f23'], type: 'vertical' },
      { id: 2, name: 'Away', colors: ['#e8ebea'], type: 'single' },
      { id: 3, name: 'Third', colors: ['#313131'], type: 'single' }
    ],
    21595: [ // AVS
      { id: 1, name: 'Home', colors: ['#e30000', '#e5e5e5'], type: 'vertical' },
      { id: 2, name: 'Away', colors: ['#f6e121'], type: 'single' },
      { id: 3, name: 'Third', colors: ['#0b1f39'], type: 'single' }
    ]
  };  