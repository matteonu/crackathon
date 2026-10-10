import { Injectable, computed, signal } from '@angular/core';

export interface CurrentUser { email:string; name:string; }

/** Who the reverse proxy says is signed in. There is no login form: see CLAUDE.md. */
@Injectable({providedIn:'root'})
export class UserStore {
  private readonly current=signal<CurrentUser|null>(null);
  readonly user=this.current.asReadonly();
  readonly name=computed(()=>this.current()?.name||'Your workspace');
  readonly subtitle=computed(()=>this.current()?.email||'Your personal workspace');
  readonly initials=computed(()=>{
    const parts=(this.current()?.name??'').split(/\s+/).filter(Boolean);
    const letters=(parts[0]?.[0]??'')+(parts.length>1?parts.at(-1)![0]:'');
    return letters.toUpperCase()||'··';
  });
  constructor(){void this.load();}
  private async load():Promise<void>{
    try{
      const response=await fetch('/api/me',{cache:'no-store'});
      if(response.ok)this.current.set(await response.json() as CurrentUser);
    }catch{/* Backend out of reach: the shell keeps the neutral placeholder. */}
  }
}
