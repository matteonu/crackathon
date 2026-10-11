import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { installPopupDismissal } from '../src/app/models/popup-dismissal.ts';

class TestNode extends EventTarget {
  children=new Set<TestNode>();
  contains(node:TestNode):boolean{return node===this||this.children.has(node);}
}
class TestDialog extends TestNode {
  open=true;
  getBoundingClientRect(){return {left:100,right:300,top:100,bottom:300};}
  close(){this.open=false;this.dispatchEvent(new Event('close'));}
}
class TestMenu extends TestNode {open=true;}
class TestDocument extends TestNode {
  defaultView=new EventTarget();
  menus:TestMenu[]=[];
  querySelectorAll(){return this.menus.filter(menu=>menu.open);}
}
const originals=new Map<string,PropertyDescriptor|undefined>();
before(()=>{
  for(const [name,value] of [['Node',TestNode],['HTMLDialogElement',TestDialog]] as const){
    originals.set(name,Object.getOwnPropertyDescriptor(globalThis,name));
    Object.defineProperty(globalThis,name,{value,configurable:true});
  }
});
after(()=>{
  for(const [name,descriptor] of originals){
    if(descriptor)Object.defineProperty(globalThis,name,descriptor);else Reflect.deleteProperty(globalThis,name);
  }
});
function emit(document:TestDocument,type:string,target:TestNode,x:number,y:number,button=0){
  const event=new Event(type);
  Object.defineProperties(event,{target:{value:target},clientX:{value:x},clientY:{value:y},button:{value:button},isPrimary:{value:true}});
  document.dispatchEvent(event);
}
function setup(){const document=new TestDocument();return {document,cleanup:installPopupDismissal(document as unknown as Document)};}

test('a backdrop click closes only the targeted dialog and fires normal close cleanup',()=>{
  const {document,cleanup}=setup();const dialog=new TestDialog(),underneath=new TestDialog();let closed=0;
  dialog.addEventListener('close',()=>closed++);
  emit(document,'pointerdown',dialog,50,50);emit(document,'click',dialog,50,50);
  assert.equal(dialog.open,false);assert.equal(closed,1);assert.equal(underneath.open,true);cleanup();
});
test('inside clicks, padding clicks, and drags starting inside keep the dialog open',()=>{
  const {document,cleanup}=setup();const dialog=new TestDialog(),child=new TestNode();
  for(const [target,startX,endX] of [[dialog,150,150],[child,150,50],[dialog,150,50],[dialog,50,150]] as const){
    emit(document,'pointerdown',target,startX,150);emit(document,'click',dialog,endX,150);
    assert.equal(dialog.open,true);
  }
  emit(document,'pointerdown',dialog,50,50,2);emit(document,'click',dialog,50,50,2);
  assert.equal(dialog.open,true);cleanup();
});
test('cancelled gestures and destroyed listeners cannot dismiss a dialog later',()=>{
  const {document,cleanup}=setup();const dialog=new TestDialog();
  emit(document,'pointerdown',dialog,50,50);document.dispatchEvent(new Event('pointercancel'));emit(document,'click',dialog,50,50);
  assert.equal(dialog.open,true);
  emit(document,'pointerdown',dialog,50,50);document.defaultView.dispatchEvent(new Event('blur'));emit(document,'click',dialog,50,50);
  assert.equal(dialog.open,true);
  cleanup();emit(document,'pointerdown',dialog,50,50);emit(document,'click',dialog,50,50);assert.equal(dialog.open,true);
});
test('upload-style popup menus stay open inside and close outside',()=>{
  const {document,cleanup}=setup();const menu=new TestMenu(),inside=new TestNode();menu.children.add(inside);document.menus.push(menu);
  emit(document,'click',inside,150,150);assert.equal(menu.open,true);
  emit(document,'click',new TestNode(),50,50);assert.equal(menu.open,false);cleanup();
});
