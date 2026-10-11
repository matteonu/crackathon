import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToString } from 'katex';
import { splitStudyText, StudyMathCache } from '../src/app/models/study-text.ts';

test('mixed prose and all four math delimiters preserve the original source',()=>{
  const text=String.raw`Bayes: \(P(A|B)\). \[\frac{x}{y}\] Also $x^2$ and $$\sum_i x_i$$.`;
  const parts=splitStudyText(text),math=parts.filter(part=>part.kind==='math');
  assert.deepEqual(math.map(part=>[part.latex,part.display]),[['P(A|B)',false],[String.raw`\frac{x}{y}`,true],['x^2',false],[String.raw`\sum_i x_i`,true]]);
  assert.equal(parts.map(part=>part.kind==='math'?part.source:part.text).join(''),text);
});
test('plain text, currency, escaped dollars, code and unmatched delimiters stay verbatim',()=>{
  for(const text of [String.raw`Costs $5 and $10.`,String.raw`Pay \$5.00.`,String.raw`Use \(unclosed`,String.raw`Use $ unclosed`,String.raw`\[unclosed`,String.raw`$$unclosed`,'Inline `$x$` code','Fence ```'+String.raw`\(x\)`+'```','<script>alert(1)</script>']){
    assert.deepEqual(splitStudyText(text),[{kind:'text',text}]);
  }
  const parts=splitStudyText('Pay $5 and $10; then solve $x^2$.');
  assert.equal(parts.filter(part=>part.kind==='math').length,1);
  assert.equal(parts.find(part=>part.kind==='math')?.latex,'x^2');
});
test('escaped closing dollars stay inside a formula and numeric formulas work',()=>{
  const parts=splitStudyText(String.raw`$x+\$5$ and $5$`);
  assert.deepEqual(parts.filter(part=>part.kind==='math').map(part=>part.latex),[String.raw`x+\$5`,'5']);
});
test('KaTeX renders accessible equations and invalid or huge equations fall back',()=>{
  const cache=new StudyMathCache();
  const html=cache.render(String.raw`\frac{x}{y}`,true,renderToString)!;
  assert.match(html,/class="katex/);assert.match(html,/<math/);assert.match(html,/<mfrac>/);
  assert.equal(cache.render(String.raw`\unsupportedCommand{a}`,false,renderToString),null);
  let called=false;assert.equal(cache.render('x'.repeat(8001),false,()=>{called=true;return '';}),null);assert.equal(called,false);
});
test('rendered math cannot introduce executable HTML or trusted links',()=>{
  const cache=new StudyMathCache();
  const html=cache.render(String.raw`\text{<img src=x onerror=alert(1)>}`,false,renderToString)!;
  assert.doesNotMatch(html,/<img|<script|<iframe/i);
  const link=cache.render(String.raw`\href{javascript:alert(1)}{click}`,false,renderToString);
  assert.doesNotMatch(link??'',/href="javascript:|<a\b/i);
});
test('cache distinguishes layout modes, reuses expressions and evicts least recently used',()=>{
  const cache=new StudyMathCache();let calls=0;const render=()=>{calls++;return '<span>equation</span>';};
  cache.render('x',false,render);cache.render('x',false,render);assert.equal(calls,1);
  cache.render('x',true,render);assert.equal(calls,2);
  for(let i=0;i<126;i++)cache.render(String(i),false,render);
  cache.render('x',false,render);cache.render('new',false,render);
  const before=calls;cache.render('x',false,render);assert.equal(calls,before);
  cache.render('x',true,render);assert.equal(calls,before+1);assert.equal(cache.size,128);
});
test('cached HTML obeys the total memory bound, not just the expression count',()=>{
  const cache=new StudyMathCache();
  for(let i=0;i<20;i++)cache.render(String(i),false,()=>'<span>'+('x'.repeat(100_000))+'</span>');
  assert.ok(cache.totalCharacters<=1_000_000);assert.ok(cache.size<20);
});
