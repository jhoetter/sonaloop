from __future__ import annotations

from .. import services
from ._html import h, raw, register_css


register_css("""
.sl-project-rico{color:var(--accent)}
.sl-project-rico svg{width:15px;height:15px}
.sl-project-title{display:flex;align-items:center;gap:10px}
.sl-project-title .sl-project-rico{width:34px;height:34px}
.sl-project-title .sl-project-rico svg{width:20px;height:20px}
.sl-project-rico-btn{border:0;padding:0;background:transparent;color:var(--accent);cursor:pointer}
.sl-project-rico-btn:focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:var(--radius)}
.sl-project-rico-btn:hover .sl-project-rico{border-color:color-mix(in srgb,var(--accent) 45%,var(--line));background:var(--accent-weak)}
.sl-icon-picker{border:0;padding:0;margin:0}
.sl-icon-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(84px,1fr));gap:8px;margin-top:8px}
.sl-icon-option{position:relative;min-width:0}
.sl-icon-option input{position:absolute;opacity:0;pointer-events:none}
.sl-icon-tile{min-height:78px;border:1px solid var(--line);border-radius:var(--radius);
  background:var(--panel-2);display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:7px;padding:9px 7px;cursor:pointer;color:var(--muted);transition:background .12s,border-color .12s,color .12s,box-shadow .12s}
.sl-icon-tile .sl-project-rico{width:34px;height:34px;color:currentColor}
.sl-icon-tile .sl-project-rico svg{width:18px;height:18px}
.sl-icon-name{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:var(--t-xs)}
.sl-icon-option input:checked+.sl-icon-tile{border-color:var(--accent);color:var(--accent);
  background:var(--accent-weak);box-shadow:0 0 0 2px color-mix(in srgb,var(--accent) 18%,transparent)}
.sl-icon-option input:focus-visible+.sl-icon-tile{outline:2px solid var(--accent);outline-offset:2px}
.sl-icon-tile:hover{border-color:color-mix(in srgb,var(--accent) 38%,var(--line));color:var(--accent)}
""")


_PROJECT_ICON_JS = """
<script>(function(){if(window.__slProjectIconEdit)return;window.__slProjectIconEdit=1;
document.addEventListener('click',function(e){
  var b=e.target.closest&&e.target.closest('[data-project-icon-trigger]');
  if(!b)return;
  e.preventDefault();
  var pid=b.getAttribute('data-project-icon-trigger');
  var dlg=null;
  document.querySelectorAll('dialog[data-project-edit]').forEach(function(d){
    if(d.getAttribute('data-project-edit')===pid)dlg=d;
  });
  if(!dlg||!dlg.showModal)return;
  dlg.showModal();
  setTimeout(function(){
    var target=dlg.querySelector('[data-icon-picker] input:checked')||dlg.querySelector('[data-icon-picker]');
    if(target&&target.focus)target.focus();
    var picker=dlg.querySelector('[data-icon-picker]');
    if(picker&&picker.scrollIntoView)picker.scrollIntoView({block:'center'});
  },0);
});
})();</script>
"""


def project_icon_html(project: dict, *, cls: str = "", edit_project_id: str | None = None,
                      edit_label: str = "Icon") -> str:
    """The stored Project/Job icon as the same framed visual used by list rows."""
    icon = h("span", {"class_": "rico sl-project-rico"}, raw(services.project_icon_svg(project, cls=cls)))
    if edit_project_id:
        return h("button", {"class_": "sl-project-rico-btn", "type": "button",
                            "data-project-icon-trigger": edit_project_id,
                            "title": edit_label, "aria-label": edit_label},
                 icon)
    return icon


def project_icon_edit_script() -> str:
    return _PROJECT_ICON_JS
