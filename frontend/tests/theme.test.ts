import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { THEMES, themeId, themeIndex, stepsToTheme, wheelMovement } from '../src/app/models/theme.ts';

test('theme selection accepts saved themes and falls back safely',()=>{
  assert.equal(THEMES.length,7);
  for(const theme of THEMES)assert.equal(themeId(theme.id),theme.id);
  for(const value of [null,undefined,'sepia',{},3,'<script>'])assert.equal(themeId(value),'green');
});

test('the wheel wraps in both directions and takes the shortest path to a clicked logo',()=>{
  assert.equal(THEMES[themeIndex(7)].id,'green');
  assert.equal(THEMES[themeIndex(-1)].id,'colorblind');
  assert.equal(THEMES[themeIndex(20)].id,'colorblind');
  assert.equal(stepsToTheme(0,'colorblind'),-1);
  assert.equal(stepsToTheme(-1,'green'),1);
  assert.equal(stepsToTheme(17,'yellow'),-2);
  assert.equal(stepsToTheme(17,'red'),0);
});

test('trackpad deltas accumulate and large scrolls advance only one theme without leftover momentum',()=>{
  let result=wheelMovement(15,0,0);
  assert.deepEqual(result,{steps:0,remainder:15});
  result=wheelMovement(35,0,result.remainder);
  assert.deepEqual(result,{steps:1,remainder:0});
  assert.deepEqual(wheelMovement(-50,0,result.remainder),{steps:-1,remainder:0});
  assert.equal(wheelMovement(3,1,0).steps,1);
  assert.deepEqual(wheelMovement(1,2,0),{steps:1,remainder:0});
  assert.deepEqual(wheelMovement(960,0,0),{steps:1,remainder:0});
  assert.deepEqual(wheelMovement(-960,0,0),{steps:-1,remainder:0});
  assert.deepEqual(wheelMovement(NaN,0,0),{steps:0,remainder:0});
});

test('the initial page paint restores every theme, ignores bad storage, and tolerates blocked storage',()=>{
  const script=readFileSync(new URL('../public/theme-init.js',import.meta.url),'utf8');
  for(const theme of THEMES){
    const document={documentElement:{dataset:{} as {theme?:string}}};
    runInNewContext(script,{document,localStorage:{getItem:()=>theme.id}});
    assert.equal(document.documentElement.dataset.theme,theme.id);
  }
  for(const getItem of [()=>'<script>',()=>null,()=>{throw new Error('Storage blocked');}]){
    const document={documentElement:{dataset:{} as {theme?:string}}};
    assert.doesNotThrow(()=>runInNewContext(script,{document,localStorage:{getItem}}));
    assert.equal(document.documentElement.dataset.theme,undefined);
  }
});

function luminance(color:string):number {
  const channels=color.slice(1).match(/../g)!.map(part=>parseInt(part,16)/255)
    .map(value=>value<=.04045?value/12.92:((value+.055)/1.055)**2.4);
  return channels[0]*.2126+channels[1]*.7152+channels[2]*.0722;
}
function contrast(a:string,b:string):number {
  const [low,high]=[luminance(a),luminance(b)].sort((x,y)=>x-y);
  return (high+.05)/(low+.05);
}

test('all themes have readable text, controls, and rating colors; high contrast text exceeds 7:1',()=>{
  const css=readFileSync(new URL('../src/themes.css',import.meta.url),'utf8');
  const tokens=(section:string)=>Object.fromEntries([...section.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})\b/g)].map(match=>[match[1],match[2]]));
  const defaults=tokens(css.match(/:root\s*\{([^}]+)\}/)![1]);
  for(const theme of THEMES){
    const palette={...defaults,...tokens(css.match(new RegExp(`\\[data-theme='${theme.id}'\\]\\s*\\{([^}]+)\\}`))![1])};
    for(const surface of ['canvas','surface','sidebar']){
      for(const foreground of ['ink','muted'])assert.ok(contrast(palette[foreground],palette[surface])>= (theme.id==='contrast'?7:4.5),`${theme.id}: ${foreground} on ${surface}`);
    }
    assert.ok(contrast(palette['on-accent'],palette.accent)>=4.5,`${theme.id}: primary buttons`);
    assert.ok(contrast(palette['table-ink'],palette['table-dark'])>=4.5,`${theme.id}: table headings`);
    assert.ok(contrast(palette['table-muted'],palette['table-dark'])>=4.5,`${theme.id}: secondary table labels`);
    for(const rating of ['rating-again','rating-hard','rating-good','rating-easy']){
      assert.ok(contrast(palette[rating],palette.surface)>=4.5,`${theme.id}: ${rating}`);
    }
  }
});
