# SPDX-License-Identifier: AGPL-3.0-only
"""Built-in acceptance checks, shared by source and both executable packages."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from pdf_compare import compare_pdfs, PROFILES, VERSION, normalize_text
from report_html import render_report


def run_self_test():
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "samples"
    cases = [
        ("internal_draft", "hospital_A_shift", True),
        ("internal_draft", "hospital_C_textwm", True),
        ("internal_draft", "hospital_E_narrow", True),
        ("internal_draft", "hospital_B_amount", False),
        ("internal_draft", "hospital_D_deleted", False),
        ("internal_draft", "hospital_F_narrow_amount", False),
        ("table_base", "table_qr_textwm", True),
        ("table_base", "table_qr_imgwm", True),
        ("table_base", "table_all_wm", True),
        ("table_base", "table_num_changed", False),
        ("table_base", "table_reordered", False),
    ]
    evidence = []
    for profile in PROFILES:
        for base, candidate, expected in cases:
            result = compare_pdfs(str(root / (base + ".pdf")),
                                  str(root / (candidate + ".pdf")), ["某某医院"], profile)
            # Four legacy fixtures contain missing glyphs in their supplied font.
            unreadable = candidate in ("hospital_B_amount", "hospital_C_textwm",
                                        "hospital_F_narrow_amount", "table_all_wm")
            valid = ((not result.passed and result.stage == "unavailable") if unreadable
                     else result.passed == expected and result.stage != "unavailable")
            evidence.append({"profile": profile, "case": candidate, "ok": valid,
                             "passed": result.passed, "stage": result.stage,
                             "diff_count": len(result.diffs)})
        for case in ("scan_only_changed", "mixed_scan_changed", "added_scan_page",
                     "top_right_contract_id", "large_font_amount", "short_hospital_party",
                     "rotated_amount", "table_cell_boundary_changed"):
            result = compare_pdfs(str(root / "regression" / (case + "_A.pdf")),
                                  str(root / "regression" / (case + "_B.pdf")), ["某某医院"], profile)
            expected_stage = "unavailable" if "scan" in case else "aligned"
            valid = not result.passed and result.stage == expected_stage
            with TemporaryDirectory(prefix="contract-acceptance-") as temp:
                report = Path(temp) / "report.html"
                render_report(result, out_path=str(report))
                content = report.read_text(encoding="utf-8")
                valid = valid and ('class="banner pass"' not in content)
                valid = valid and (f"比较档位：{PROFILES[profile][0]}" in content)
            evidence.append({"profile": profile, "case": case, "ok": valid,
                             "passed": result.passed, "stage": result.stage,
                             "diff_count": len(result.diffs)})
        # Baseline extraction and original file fingerprints must survive all modes.
        result = compare_pdfs(str(root / "table_base.pdf"), str(root / "table_base.pdf"),
                              ["某某医院"], profile)
        evidence.append({"profile": profile, "case": "self_compare", "ok": result.passed
                         and len(result.source_a_hash) == 64 and not result.a_watermarks})
    evidence.append({"case": "strict_semantic_space", "ok":
                     normalize_text("AB C", profile="strict") != normalize_text("A BC", profile="strict")})
    evidence.append({"case": "strict_superscript", "ok":
                     normalize_text("m²", profile="strict") != normalize_text("m2", profile="strict")})
    return {"version": VERSION, "passed": all(row["ok"] for row in evidence),
            "passed_count": sum(row["ok"] for row in evidence), "total_count": len(evidence),
            "checks": evidence}


if __name__ == "__main__":
    result = run_self_test()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["passed"] else 1)
