import { DestroyRef, Injectable, inject } from '@angular/core';
import { StudyMathCache } from '../models/study-text';

@Injectable({providedIn:'root'})
export class StudyMathService {
  private engine:Promise<typeof import('katex')>|undefined;
  private readonly cache=new StudyMathCache();
  private readonly waiting=new Map<Element,()=>void>();
  private observer:IntersectionObserver|undefined;
  constructor(){inject(DestroyRef).onDestroy(()=>{this.observer?.disconnect();this.waiting.clear();});}
  whenVisible(element:Element,render:()=>void):()=>void{
    if(typeof IntersectionObserver==='undefined'){render();return ()=>{};}
    this.observer??=new IntersectionObserver(entries=>{
      for(const entry of entries){
        if(!entry.isIntersecting)continue;
        const callback=this.waiting.get(entry.target);this.waiting.delete(entry.target);this.observer?.unobserve(entry.target);callback?.();
      }
    },{rootMargin:'200px'});
    this.waiting.set(element,render);this.observer.observe(element);
    return ()=>{this.waiting.delete(element);this.observer?.unobserve(element);};
  }
  async render(latex:string,display:boolean):Promise<string|null>{
    try{
      this.engine??=import('katex').catch(error=>{this.engine=undefined;throw error;});
      const engine=await this.engine;
      return this.cache.render(latex,display,engine.renderToString);
    }catch{return null;}
  }
}
