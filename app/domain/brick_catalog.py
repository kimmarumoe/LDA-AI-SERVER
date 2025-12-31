from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


BrickType = str


@dataclass(frozen=True)
class BrickShape:
    """
    타일링에서 검사하는 '방향 포함' 도형.
    type은 '1x4' 같은 정규 타입을 유지하고, (w,h)만 회전으로 바뀐다.
    """
    type: BrickType
    w: int
    h: int


class BrickCatalog:
    """
    - 지원 브릭 목록의 단일 소스(SSOT)
    - 입력 검증/정규화
    - 회전 포함 shape 생성
    """

    _SUPPORTED: Dict[BrickType, Tuple[int, int]] = {
        "1x1": (1, 1),
        "1x2": (2, 1),
        "1x3": (3, 1),
        "1x4": (4, 1),
        "1x5": (5, 1),
        "2x2": (2, 2),
        "2x3": (3, 2),
        "2x4": (4, 2),
        "2x5": (5, 2),
    }

    @classmethod
    def supported_types(cls) -> List[BrickType]:
        return list(cls._SUPPORTED.keys())

    @classmethod
    def normalize(cls, types: List[str] | None) -> List[BrickType]:
        """
        - 중복 제거
        - 소문자/공백 정리
        - 미지원 타입 차단
        - 1x1은 항상 포함(필수 안전장치)
        """
        if not types:
            return ["1x1"]

        uniq: List[BrickType] = []
        for t in types:
            key = str(t).strip().lower()
            if key not in cls._SUPPORTED:
                raise ValueError(f"Unsupported brick type: {t}")
            if key not in uniq:
                uniq.append(key)

        if "1x1" not in uniq:
            uniq.insert(0, "1x1")

        return uniq

    @classmethod
    def shapes_for(cls, types: List[BrickType]) -> List[BrickShape]:
        """
        - 회전 가능한 도형은 (w,h) + (h,w) 둘 다 제공
        - 큰 면적 우선 정렬(그리디 품질 개선)
        """
        shapes: List[BrickShape] = []
        for t in types:
            w, h = cls._SUPPORTED[t]
            shapes.append(BrickShape(t, w, h))
            if w != h:
                shapes.append(BrickShape(t, h, w))  # 회전

        # 면적 우선(큰 것 먼저), 같은 면적이면 긴 변 큰 것 먼저
        shapes.sort(key=lambda s: (s.w * s.h, max(s.w, s.h)), reverse=True)
        return shapes
