export const THEMES = [
  {id:'green', label:'Green'},
  {id:'yellow', label:'Yellow'},
  {id:'blue', label:'Blue'},
  {id:'red', label:'Red'},
  {id:'dark', label:'Dark mode'},
  {id:'contrast', label:'High contrast dark'},
  {id:'colorblind', label:'Color blind'},
] as const;

export type ThemeId = typeof THEMES[number]['id'];
export const THEME_STORAGE_KEY = 'studyhub.theme';

export function themeId(value:unknown):ThemeId {
  return THEMES.some(theme=>theme.id===value) ? value as ThemeId : 'green';
}

export function themeIndex(step:number):number {
  return ((step % THEMES.length) + THEMES.length) % THEMES.length;
}

/** Select the closest turn of the wheel, including crossing its Green/Color blind seam. */
export function stepsToTheme(step:number,id:ThemeId):number {
  let delta=THEMES.findIndex(theme=>theme.id===id)-themeIndex(step);
  if(delta>THEMES.length/2)delta-=THEMES.length;
  if(delta< -THEMES.length/2)delta+=THEMES.length;
  return delta;
}

/** Small trackpad deltas accumulate; each completed scroll advances exactly one theme. */
export function wheelMovement(delta:number,mode:number,remainder:number):{steps:number;remainder:number} {
  if(!Number.isFinite(delta)||!Number.isFinite(remainder))return {steps:0,remainder:0};
  const pixels=delta*(mode===1?16:mode===2?240:1)+remainder;
  if(Math.abs(pixels)<48)return {steps:0,remainder:pixels||0};
  return {steps:Math.sign(pixels),remainder:0};
}
