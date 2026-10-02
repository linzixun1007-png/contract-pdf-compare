# SPDX-License-Identifier: AGPL-3.0-only
"""Behavioral acceptance checks for comparison scope and truthful reports."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from ignore_regions import IgnoreConfig, IgnoreRegion, margin_preset, parse_pages
from pdf_compare import (PROFILES, TextLine, fitz, compare_pdfs, extract_with_regions,
                         _build_units, _unit_original_text, normalize_text)
from report_html import _char_diff, render_report

def run_region_checks(samples):
    root = Path(samples) / "regression_v12"
    checks = []
    def record(case, ok, profile=None):
        checks.append({"case": case, "ok": bool(ok), **({"profile":profile} if profile else {})})
    def compare(a, b, config=None, profile="regular"):
        return compare_pdfs(str(root / (a+".pdf")), str(root / (b+".pdf")),
                            profile=profile, ignore_config=config)
    def fails(action):
        try:
            action()
        except (ValueError, OSError, KeyError, TypeError):
            return True
        return False
    def word_box(name, target, rotation=False):
        with fitz.open(root / (name+".pdf")) as doc:
            page = doc[0]
            box = page.search_for(target)[0]
            if rotation:
                box = box * page.rotation_matrix
            return tuple(box), page.rect.width, page.rect.height
    def around_words(a, b, old, new, rotation=False):
        box_a,w,h = word_box(a, old, rotation)
        box_b,_,_ = word_box(b, new, rotation)
        box = fitz.Rect(box_a) | fitz.Rect(box_b)
        return IgnoreConfig([IgnoreRegion("Stamp", ((box.x0-.1)/w, (box.y0-.1)/h,
                                                    (box.x1+.1)/w, (box.y1+.1)/h))])

    margins = margin_preset()
    word_mask = around_words("glyph_A", "glyph_B", "ABC", "XYZ")
    bx,w,h = word_box("glyph_A", "ABC")
    partial = IgnoreConfig([IgnoreRegion("Partial glyph", (bx[0]/w, bx[1]/h,
                                  (bx[0]+1)/w, (bx[3]+.1)/h))])
    for profile in PROFILES:
        before = compare("reflow_A", "reflow_B", profile=profile)
        after = compare("reflow_A", "reflow_B", margins, profile)
        edit = compare("reflow_A", "body_change_B", margins, profile)
        excluded = compare("excluded_A", "excluded_B", margins, profile)
        glyph = compare("glyph_A", "glyph_B", partial, profile)
        masked = compare("glyph_A", "glyph_B", word_mask, profile)
        sizes = compare("sizes_A", "sizes_B", margins, profile)
        record("reflow_without_scope_is_flagged", not before.passed and before.stage=="aligned", profile)
        record("cross_page_reflow_with_explicit_margins", after.passed and after.page_counts==(2,3), profile)
        record("body_amount_change_outside_scope", not edit.passed and edit.stage=="aligned"
               and any("900" in d.new for d in edit.diffs), profile)
        record("excluded_change_is_separately_reported", excluded.passed and excluded.excluded_differences
               and excluded.a_ignored and excluded.b_ignored, profile)
        record("partially_intersected_glyph_remains_compared", not glyph.passed and glyph.stage=="aligned", profile)
        record("partial_line_exclusion_preserves_remainder", masked.passed
               and any("Pay USD 100" in l.text for l in masked.a_lines)
               and all("Pay USD 100" not in l.text for l in masked.a_ignored), profile)
        record("percentage_masks_on_different_page_sizes", sizes.passed and sizes.excluded_differences, profile)

    first_page = IgnoreConfig([IgnoreRegion("Footer", (0,.92,1,1), pages=(1,))])
    record("page_restriction_preserves_other_page_edits",
           not compare("page_scope_A", "page_scope_B", first_page).passed)
    record("all_page_scope_applies_to_each_page", compare("page_scope_A", "page_scope_B", margins).passed)
    a_only = IgnoreConfig([IgnoreRegion("Header",(0,0,1,.10),side="A")])
    b_only = IgnoreConfig([IgnoreRegion("Header",(0,0,1,.10),side="B")])
    record("independent_A_mask", compare("side_A", "side_B", a_only).passed)
    record("wrong_side_does_not_hide_A_text", not compare("side_A", "side_B", b_only).passed)
    rotated = around_words("rotated_A", "rotated_B", "Stamp ABC", "Stamp XYZ", True)
    record("preview_coordinates_match_rotated_PDF", compare("rotated_A", "rotated_B", rotated).passed)
    whole = IgnoreConfig([IgnoreRegion("All",(0,0,1,1))])
    erased = compare("excluded_A", "excluded_B", whole)
    scan = compare("scan_mask_A", "scan_mask_B", whole)
    record("empty_comparison_scope_never_passes", not erased.passed and erased.stage=="unavailable")
    record("scan_cannot_be_made_to_pass_by_masking", not scan.passed and scan.stage=="unavailable")
    outside = IgnoreConfig([IgnoreRegion("Missing page",(0,0,1,.1), pages=(9,))])
    record("missing_page_is_rejected", fails(lambda:compare("excluded_A","excluded_B",outside)))
    record("zero_area_is_rejected", fails(lambda:IgnoreRegion("Invalid",(.2,.3,.2,.4))))
    record("out_of_page_is_rejected", fails(lambda:IgnoreRegion("Invalid",(0,0,1,1.1))))
    record("unsupported_schema_is_rejected", fails(lambda:IgnoreConfig.from_dict(
        {"schema_version":2,"coordinates":"page_fraction","regions":[]})))
    record("unsupported_coordinate_system_is_rejected", fails(lambda:IgnoreConfig.from_dict(
        {"schema_version":1,"coordinates":"pixels","regions":[]})))
    record("physical_page_selection", parse_pages("1,3-5")== (1,3,4,5)
           and fails(lambda:parse_pages("0,2")) and fails(lambda:parse_pages("5-3")))
    with TemporaryDirectory(prefix="contract-regions-") as temp:
        path = Path(temp)/"rules.json"
        margins.save(path)
        record("rules_round_trip_contains_geometry_only", IgnoreConfig.load(path).to_dict()==margins.to_dict()
               and not any(value in path.read_text(encoding="utf-8") for value in (".pdf","Payments")))
        record("missing_rules_file_is_rejected", fails(lambda:IgnoreConfig.load(Path(temp)/"missing.json")))
        result = compare("excluded_A", "excluded_B", margins)
        report = Path(temp)/"report.html"
        render_report(result, out_path=str(report))
        content = report.read_text(encoding="utf-8")
        record("report_limits_pass_to_compared_scope", "指定忽略区域以外" in content
               and "Approved reference" in content and "Changed reference" in content
               and "有（单独复核）" in content)

    lines = [TextLine(0,"First clause; Second clause;",normalize_text("First clause; Second clause;"),
                      0,0,400,20,11,(1,0)),
             TextLine(1,"Third clause;",normalize_text("Third clause;"),0,0,200,20,11,(1,0))]
    units = _build_units(lines)
    rendered = [_unit_original_text(u) for u in units]
    record("report_never_repeats_adjacent_sentence", rendered==["First clause;","Second clause;","Third clause;"])
    old,new = _char_diff("Pay USD 100;", "Pay  USD 100;", "regular")
    record("ignored_whitespace_has_no_change_highlight", "<del>" not in old and "<ins>" not in new)
    old,new = _char_diff("Pay USD 100;", "Pay  USD 900;", "regular")
    record("amount_highlight_tracks_actual_edit", "<del>1</del>" in old and "<ins>9</ins>" in new
           and "<ins> </ins>" not in new)
    old,new = _char_diff("Limit １００;", "Limit 100;", "regular")
    record("normalized_full_width_has_no_change_highlight", "<del>" not in old and "<ins>" not in new)
    return checks
