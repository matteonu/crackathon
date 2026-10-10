import { Component, input } from '@angular/core';

const paths:Record<string,string> = {
  folder:'M3 7V4h6l3 3h9v13H3z',
  'folder-open':'M3 10V4h6l3 3h8v3 M3 10h19l-3 10H3z',
  'folder-plus':'M3 7V4h6l3 3h9v13H3z M12 10v7 M8.5 13.5h7',
  cards:'M7 7h14v14H7z M3 17V3h14 M11 12h6 M11 16h4',
  play:'M6 3l15 9-15 9z',
  down:'M5 9l7 7 7-7',
  grid:'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  calendar:'M8 2v4 M16 2v4 M3 10h18 M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2 M7 14h2 M12 14h2 M7 18h2',
  book:'M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1v15',
  chart:'M4 3v17h17 M8 16v-5 M13 16V7 M18 16V4',
  check:'M5 12l4 4L19 6',
  arrow:'M5 12h14 M13 6l6 6-6 6',
  expand:'M14 3h7v7 M21 3l-8 8 M10 21H3v-7 M3 21l8-8',
  plus:'M12 5v14 M5 12h14',
  close:'M6 6l12 12 M18 6L6 18',
  trash:'M3 6h18 M9 6V3h6v3 M5 6l1 15h12l1-15 M10 10v7 M14 10v7',
  left:'M15 5l-7 7 7 7',
  right:'M9 5l7 7-7 7',
  clock:'M12 8v5l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  download:'M12 3v12 M7 10l5 5 5-5 M4 16v5h16v-5',
  upload:'M12 16V4 M7 9l5-5 5 5 M4 16v5h16v-5',
  logout:'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4 M16 17l5-5-5-5 M21 12H9',
  settings:'M4 7h16 M4 17h16 M8 4v6 M16 14v6',
  flag:'M5 22V3 M5 3c5-4 9 4 15 0v10c-6 4-10-4-15 0',
  leaf:'M20 4C6 2 1 8 6 16c6 7 15 2 14-12Z M4 21L16 9',
  menu:'M4 6h16 M4 12h16 M4 18h16'
};

@Component({selector:'app-icon',standalone:true,template:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path [attr.d]="paths[name()] || paths[\'grid\']" /></svg>',styles:':host{display:inline-flex;flex-shrink:0;width:20px;height:20px}svg{width:100%;height:100%}'})
export class IconComponent { readonly name=input('grid'); readonly paths=paths; }
