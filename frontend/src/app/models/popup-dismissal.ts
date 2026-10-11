/** Shared native listeners cover dialogs added anywhere in the app, without
 * triggering Angular checks for ordinary pointer activity. */
export function installPopupDismissal(document:Document):()=>void{
  const window=document.defaultView;if(!window)return ()=>{};
  const listeners=new AbortController();
  let pressedBackdrop:HTMLDialogElement|null=null;
  const outside=(dialog:HTMLDialogElement,event:MouseEvent):boolean=>{
    const rect=dialog.getBoundingClientRect();
    return event.clientX<rect.left||event.clientX>=rect.right||event.clientY<rect.top||event.clientY>=rect.bottom;
  };
  const reset=()=>{pressedBackdrop=null;};
  const down=(event:PointerEvent)=>{
    reset();
    const target=event.target;
    if(event.button===0&&event.isPrimary!==false&&target instanceof HTMLDialogElement&&target.open&&outside(target,event))pressedBackdrop=target;
  };
  const click=(event:MouseEvent)=>{
    const dialog=pressedBackdrop;reset();
    if(dialog&&dialog.open&&event.target===dialog&&outside(dialog,event))dialog.close();
    if(event.target instanceof Node){
      for(const menu of document.querySelectorAll<HTMLDetailsElement>('details[data-popup][open]')){
        if(!menu.contains(event.target))menu.open=false;
      }
    }
  };
  const options={capture:true,signal:listeners.signal};
  document.addEventListener('pointerdown',down,options);
  document.addEventListener('click',click,options);
  document.addEventListener('pointercancel',reset,options);
  window.addEventListener('blur',reset,{signal:listeners.signal});
  return ()=>{reset();listeners.abort();};
}
