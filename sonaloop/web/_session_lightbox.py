"""Browser controller for the session screenshot lightbox.

Kept separate from the session page renderer so the replay surface can stay focused on its
server-rendered timeline.  The script is idempotent because drawer fragments may execute it again.
"""

# Every ``[data-lightbox]`` anchor opens its full-resolution step shot in a native dialog.
# The dialog is a direct child of ``body`` so it enters the top layer above drawers and iframes.
# Button, Escape and backdrop close it; focus then returns to the originating screenshot.
LIGHTBOX_JS = """<script>(function(){
if(window.__slLightbox) return; window.__slLightbox=1;
var activeTrigger=null;
function finishLightbox(dlg){
  var trigger=activeTrigger; activeTrigger=null;
  if(dlg&&dlg.isConnected) dlg.remove();
  if(trigger&&trigger.isConnected&&trigger.focus) trigger.focus();
}
function closeLightbox(dlg){
  if(!dlg || !dlg.hasAttribute('open')) return;
  if(dlg.close) dlg.close();
  else{ dlg.removeAttribute('open'); finishLightbox(dlg); }
}
document.addEventListener('click',function(e){
  var a=e.target.closest&&e.target.closest('[data-lightbox]'); if(!a) return;
  e.preventDefault();
  var dlg=document.getElementById('sl-lightbox');
  if(!dlg){
    dlg=document.createElement('dialog'); dlg.id='sl-lightbox'; dlg.className='sl-lightbox';
    var fig=document.createElement('figure'); fig.className='sl-lb-fig';
    fig.appendChild(document.createElement('img'));
    var x=document.createElement('button'); x.type='button'; x.className='sl-lb-close';
    x.setAttribute('aria-label','Close'); x.textContent='\\u00d7';
    fig.appendChild(x);
    var cap=document.createElement('figcaption'); cap.className='sl-lb-cap';
    cap.id='sl-lb-cap'; dlg.setAttribute('aria-describedby',cap.id);
    fig.appendChild(cap);
    dlg.appendChild(fig);
    x.addEventListener('click',function(ev){ ev.preventDefault(); ev.stopPropagation(); closeLightbox(dlg); });
    dlg.addEventListener('click',function(ev){ if(ev.target===dlg) closeLightbox(dlg); });
    dlg.addEventListener('cancel',function(ev){ ev.preventDefault(); closeLightbox(dlg); });
    dlg.addEventListener('close',function(){ finishLightbox(dlg); });
  }
  if(!dlg.isConnected||dlg.parentNode!==document.body) document.body.appendChild(dlg);
  activeTrigger=a;
  var img=dlg.querySelector('img'), thumb=a.querySelector('img'), cap=dlg.querySelector('.sl-lb-cap'),
      close=dlg.querySelector('.sl-lb-close');
  img.src=a.getAttribute('href'); img.alt=(thumb&&thumb.alt)||'';
  cap.textContent=a.getAttribute('data-caption')||(thumb&&thumb.alt)||'';
  cap.style.display=cap.textContent?'':'none';
  close.setAttribute('aria-label',a.getAttribute('data-close-label')||'Close');
  if(dlg.showModal){ if(!dlg.open) dlg.showModal(); }
  else dlg.setAttribute('open','');
  setTimeout(function(){ if(close&&close.focus) close.focus(); },0);
});
document.addEventListener('keydown',function(e){
  if(e.key==='Escape') closeLightbox(document.getElementById('sl-lightbox'));
});
})();</script>"""
