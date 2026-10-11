import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector:'app-generation-loader',standalone:true,changeDetection:ChangeDetectionStrategy.OnPush,
  host:{'[class.compact]':'compact()','[class.icon-only]':'iconOnly()'},
  template:`<span class="generation-loader" role="status" [attr.aria-label]="label()"><span class="cat-window" aria-hidden="true"><img src="assets/loading/generation-cat.gif" width="1240" height="698" alt="" decoding="async"><span class="motion-fallback">🐈</span></span>@if(!iconOnly()){<span>{{label()}}</span>}</span>`,
  styles:`
    :host{display:inline-flex;vertical-align:middle;max-width:100%;}
    .generation-loader{display:inline-flex;align-items:center;gap:7px;max-width:100%;line-height:1.4;}
    .cat-window{position:relative;display:inline-block;flex:none;width:60px;height:30px;overflow:hidden;border-radius:4px;background:var(--surface);}
    /* The cat stays within x=400..800, y=300..500 in every original GIF frame. */
    img{position:absolute;width:310%;height:349%;max-width:none;left:-100%;top:-150%;mix-blend-mode:multiply;}
    :host(.compact) .cat-window{width:40px;height:20px;}
    :host(.icon-only) .cat-window{width:20px;height:10px;}
    :host-context([data-theme='dark']) img,:host-context([data-theme='contrast']) img{filter:invert(1);mix-blend-mode:screen;}
    .motion-fallback{display:none;align-items:center;justify-content:center;width:100%;height:100%;font-size:14px;}
    @media(prefers-reduced-motion:reduce){img{display:none;}.motion-fallback{display:flex;}}
  `,
})
export class GenerationLoaderComponent {
  readonly label=input('Generating…');readonly compact=input(false);readonly iconOnly=input(false);
}
