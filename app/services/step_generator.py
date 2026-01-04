# app/services/step_generator.py
from __future__ import annotations

from typing import List, Dict, Any, Tuple


def _sort_key(p: Dict[str, Any]) -> Tuple[int, int, int, int]:
    # 안정적인 순서를 위해 (y, x, w, h)
    return (int(p.get("y", 0)), int(p.get("x", 0)), int(p.get("w", 1)), int(p.get("h", 1)))


def generate_steps_by_rows(
    placements: List[Dict[str, Any]],
    rows_per_step: int = 2,
    max_placements_per_step: int = 256,
) -> List[Dict[str, Any]]:
    """
    placements를 행(y) 기준으로 묶어서 steps를 만든다.

    rows_per_step:
      - 1이면 1행당 1스텝(스텝 수 많아짐)
      - 2~4 정도가 보기 좋음(48x48이면 12~24스텝)

    max_placements_per_step:
      - 한 스텝이 너무 커지는 것 방지(프론트 렌더 부담 감소)
    """
    if not placements:
        return []

    rows_per_step = max(1, int(rows_per_step))
    max_placements_per_step = max(16, int(max_placements_per_step))

    sorted_list = sorted(placements, key=_sort_key)

    # y별로 그룹핑
    rows: Dict[int, List[Dict[str, Any]]] = {}
    for p in sorted_list:
        y = int(p.get("y", 0))
        rows.setdefault(y, []).append(p)

    ys = sorted(rows.keys())

    steps: List[Dict[str, Any]] = []
    step_index = 1

    # rows_per_step 단위로 y 묶기
    for i in range(0, len(ys), rows_per_step):
        y_chunk = ys[i : i + rows_per_step]
        chunk_placements: List[Dict[str, Any]] = []
        for y in y_chunk:
            chunk_placements.extend(rows[y])

        # 너무 많으면 한번 더 쪼갬
        for j in range(0, len(chunk_placements), max_placements_per_step):
            part = chunk_placements[j : j + max_placements_per_step]
            min_y = min(y_chunk)
            max_y = max(y_chunk)

            steps.append(
                {
                    "index": step_index,
                    "title": f"{step_index}단계",
                    "description": f"{min_y}~{max_y}행 배치",
                    "placements": part,
                }
            )
            step_index += 1

    return steps
