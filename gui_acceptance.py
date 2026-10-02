# SPDX-License-Identifier: AGPL-3.0-only
"""Exercise this application's own Tk widgets with invented PDF fixtures."""
from pathlib import Path
from types import SimpleNamespace
import sys
from ignore_regions import IgnoreConfig

def check_region_editor(root, app):
    from region_editor import RegionEditor
    import gui
    sample = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "samples/regression_v12"
    applied, checks = [], []
    original = IgnoreConfig()
    editor = RegionEditor(root, str(sample/"reflow_A.pdf"), str(sample/"reflow_B.pdf"),
                          original, applied.append)
    editor.window.withdraw()
    checks.append({"case":"both_local_previews_render", "ok":set(editor.images)=={"A","B"}})
    editor.side.set("仅 A")
    editor.scope.set("当前页")
    editor.turn("A",1)
    x,y,w,h = editor.frames["A"]
    editor.begin_drag("A",SimpleNamespace(x=x+w*.2,y=y+h*.2))
    editor.move_drag("A",SimpleNamespace(x=x+w*.3,y=y+h*.4))
    editor.end_drag("A",SimpleNamespace(x=x+w*.3,y=y+h*.4))
    selected = editor.config.regions[0]
    checks.append({"case":"drag_coordinates_and_current_page", "ok":selected.side=="A"
                   and selected.pages==(2,) and all(abs(a-b)<1e-6 for a,b in
                     zip(selected.rect,(.2,.2,.3,.4)))})
    checks.append({"case":"editing_does_not_mutate_active_rules", "ok":not original.regions})
    editor.side.set("仅 B")
    editor.add_margins()
    checks.append({"case":"margin_preset_and_side", "ok":len(editor.config.regions)==3
                   and all(r.side=="B" and r.pages==() for r in editor.config.regions[1:])})
    editor.apply()
    checks.append({"case":"apply_commits_and_closes_PDFs", "ok":len(applied)==1
                   and len(applied[0].regions)==3 and all(d.is_closed for d in editor.docs.values())})
    cancelled = RegionEditor(root,str(sample/"reflow_A.pdf"),str(sample/"reflow_B.pdf"),
                              original,applied.append)
    cancelled.window.withdraw()
    cancelled.add_margins()
    cancelled.close()
    checks.append({"case":"cancel_does_not_commit", "ok":len(applied)==1 and not original.regions})
    app.var_a.set(str(sample/"reflow_A.pdf"))
    app.var_b.set(str(sample/"reflow_B.pdf"))
    app.ignore_config = applied[0]
    app.rules_source_paths = app.file_pair()
    app.var_b.set(str(sample/"body_change_B.pdf"))
    warnings = []
    previous = gui.messagebox.showwarning
    gui.messagebox.showwarning = lambda *args,**kwargs:warnings.append(args)
    try:
        app.start()
    finally:
        gui.messagebox.showwarning = previous
    checks.append({"case":"changed_file_pair_requires_region_review", "ok":len(warnings)==1
                   and warnings[0][0]=="请重新预览区域" and app.btn.cget("state")=="normal"})
    app.clear_regions()
    checks.append({"case":"clear_returns_to_full_text_scope", "ok":not app.ignore_config.regions
                   and app.rules_source_paths is None})
    return checks
