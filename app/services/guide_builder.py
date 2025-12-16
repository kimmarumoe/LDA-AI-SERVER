# app/services/guide_builder.py
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

# 프로젝트 스키마에 맞게 import 경로만 조정해줘
from app.schemas.guide import GuideBrick, GuideStep, PaletteItem


@dataclass(frozen=True)
class StepStrategy:
    """조립 순서 생성 전략(확장 포인트)"""
    name: str = "row"


class GuideBuilder:
    """
    grid + palette로부터
    1) 브릭 목록(inventory)
    2) 조립 순서(steps)
    를 생성하는 서비스

    - SRP: '가이드 생성'만 담당
    - OCP: step 전략 교체 가능
    """

    def __init__(self, step_strategy: StepStrategy | None = None) -> None:
        self._strategy = step_strategy or StepStrategy()

    def build_inventory(self, grid: List[List[int]], palette: List[PaletteItem]) -> List[GuideBrick]:
        """
        grid: 팔레트 인덱스(정수) 2차원 배열
        palette: 인덱스에 대응되는 색상/이름/hex 목록
        """
        counter = Counter()
        for row in grid:
            counter.update(row)

        bricks: List[GuideBrick] = []
        for palette_index, count in sorted(counter.items(), key=lambda x: x[0]):
            if palette_index < 0 or palette_index >= len(palette):
                continue

            p = palette[palette_index]
            # MVP: 1셀 = 1x1 타일(혹은 플레이트)로 고정
            bricks.append(
                GuideBrick(
                    type="tile_1x1",
                    color=p.hex,
                    name=getattr(p, "name", None) or f"Color {palette_index}",
                    count=count,
                )
            )

        return bricks

    def build_steps(self, grid: List[List[int]], palette: List[PaletteItem]) -> List[GuideStep]:
        """
        MVP: 행(row) 단위로 조립 순서를 생성
        """
        steps: List[GuideStep] = []
        height = len(grid)

        for y in range(height):
            row = grid[y]
            c = Counter(row)

            # 사람이 읽기 좋게 "색상명: 개수" 텍스트 생성
            parts: List[str] = []
            for palette_index, count in sorted(c.items(), key=lambda x: x[0]):
                if palette_index < 0 or palette_index >= len(palette):
                    continue
                p = palette[palette_index]
                color_name = getattr(p, "name", None) or p.hex
                parts.append(f"{color_name} {count}개")

            steps.append(
                GuideStep(
                    title=f"{y + 1}행 배치",
                    description=" · ".join(parts) if parts else "배치 없음",
                    hint="왼쪽에서 오른쪽 순서로 배치하세요.",
                )
            )

        return steps
