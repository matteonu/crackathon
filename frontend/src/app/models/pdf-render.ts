/** Match displayed size without allocating oversized canvases for large PDF pages. */
export function pdfRenderScale(width:number,height:number,displayWidth:number,pixelRatio:number):number{
  const desired=displayWidth*Math.min(2,Math.max(1,pixelRatio))/width;
  return Math.min(desired,Math.sqrt(4_000_000/(width*height)),8192/width,8192/height);
}

/** Bounded cache of retired page resources. Taking an entry transfers ownership to its renderer. */
export class PdfPageCache<T extends {pixels:number}> {
  private readonly entries=new Map<string,T>();
  private pixels=0;
  private closed=false;
  private readonly dispose:(value:T)=>void;
  constructor(dispose:(value:T)=>void){this.dispose=dispose;}
  get size():number{return this.entries.size;}
  get totalPixels():number{return this.pixels;}
  get isClosed():boolean{return this.closed;}
  take(key:string):T|undefined{
    const entry=this.entries.get(key);
    if(entry){this.entries.delete(key);this.pixels-=entry.pixels;}
    return entry;
  }
  put(key:string,entry:T):void{
    const old=this.take(key);if(old)this.dispose(old);
    if(this.closed||entry.pixels>8_000_000){this.dispose(entry);return;}
    this.entries.set(key,entry);this.pixels+=entry.pixels;
    while(this.entries.size>6||this.pixels>8_000_000){
      const oldest=this.entries.keys().next().value!;
      this.dispose(this.take(oldest)!);
    }
  }
  close():void{
    this.closed=true;
    for(const entry of this.entries.values())this.dispose(entry);
    this.entries.clear();this.pixels=0;
  }
}

export interface CachedPdfPage {canvas:HTMLCanvasElement;pixels:number;text:string|null;aspect:number;}
export function createPdfPageCache():PdfPageCache<CachedPdfPage>{
  return new PdfPageCache(entry=>{entry.canvas.width=1;entry.canvas.height=1;});
}
