# SPDX-License-Identifier: AGPL-3.0-only
"""Validated, portable geometry rules. No PDF contents or file paths are saved."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import json
import math

@dataclass(frozen=True)
class IgnoreRegion:
    name: str
    rect: tuple[float, float, float, float]
    side: str = "both"
    pages: tuple[int, ...] = ()

    def __post_init__(self):
        if self.side not in ("A", "B", "both"):
            raise ValueError("区域适用文件必须是 A、B 或 both")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("区域名称不能为空")
        if len(self.rect) != 4 or any(isinstance(n, bool) or not isinstance(n, (int, float))
                                     or not math.isfinite(n) or not 0 <= n <= 1 for n in self.rect):
            raise ValueError("区域坐标须为 0 到 1 之间的四个有限数值")
        x0, y0, x1, y1 = self.rect
        if x0 >= x1 or y0 >= y1:
            raise ValueError("区域宽度和高度必须大于零")
        if any(isinstance(p, bool) or not isinstance(p, int) or p < 1 for p in self.pages):
            raise ValueError("页码须为从 1 开始的整数；留空表示全部页")

    def applies(self, side, page):
        return self.side in (side, "both") and (not self.pages or page + 1 in self.pages)

    def contains(self, box, width, height):
        x0, y0, x1, y1 = self.rect
        bx0, by0, bx1, by1 = box
        return (bx0 >= x0 * width - .01 and by0 >= y0 * height - .01
                and bx1 <= x1 * width + .01 and by1 <= y1 * height + .01)

    def to_dict(self):
        return {"name": self.name, "side": self.side, "pages": list(self.pages), "rect": list(self.rect)}

@dataclass
class IgnoreConfig:
    regions: list[IgnoreRegion] = field(default_factory=list)

    def matching(self, side, page):
        return [r for r in self.regions if r.applies(side, page)]

    def to_dict(self):
        return {"schema_version": 1, "coordinates": "page_fraction", "regions": [r.to_dict() for r in self.regions]}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("coordinates") != "page_fraction":
            raise ValueError("不支持的区域规则格式")
        values = data.get("regions")
        if not isinstance(values, list):
            raise ValueError("区域规则应包含 regions 列表")
        result = []
        for value in values:
            if not isinstance(value, dict):
                raise ValueError("区域规则必须是对象")
            result.append(IgnoreRegion(value["name"], tuple(value["rect"]), value.get("side", "both"),
                                       tuple(value.get("pages", []))))
        return cls(result)

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8-sig")))

    def save(self, path):
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def validate_pages(self, counts):
        for region in self.regions:
            for side in ("A", "B"):
                if region.side in (side, "both") and any(p > counts[side] for p in region.pages):
                    raise ValueError(f"区域「{region.name}」指定了 {side} 文件不存在的页码")

def margin_preset(top=0.10, bottom=0.08, side="both"):
    return IgnoreConfig([IgnoreRegion("页眉", (0, 0, 1, top), side),
                         IgnoreRegion("页脚和页码", (0, 1-bottom, 1, 1), side)])

def parse_pages(value):
    if not value.strip():
        return ()
    pages = set()
    for token in value.replace("，", ",").split(","):
        parts = token.strip().split("-")
        if len(parts) == 1:
            pages.add(int(parts[0]))
        elif len(parts) == 2:
            first, last = map(int, parts)
            if first < 1 or last < first or last-first > 10000:
                raise ValueError("页码范围无效")
            pages.update(range(first, last+1))
        else:
            raise ValueError("页码示例：1,3-5；留空为全部页")
    if any(p < 1 for p in pages):
        raise ValueError("页码须从 1 开始")
    return tuple(sorted(pages))
