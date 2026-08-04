from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class GoldStandardFixture:
    fixture_id: str
    name: str
    vertices: List[Tuple[float, float]]
    expected_area_m2: float
    expected_far: float = 0.0
    expected_density: float = 0.0

GS_001_SQUARE = GoldStandardFixture(
    fixture_id="GS-001",
    name="Square Parcel 100m x 100m",
    vertices=[(0, 0), (100, 0), (100, 100), (0, 100)],
    expected_area_m2=10000.0,
)

GS_002_RECTANGLE = GoldStandardFixture(
    fixture_id="GS-002",
    name="Rectangle 200m x 50m",
    vertices=[(0, 0), (200, 0), (200, 50), (0, 50)],
    expected_area_m2=10000.0,
)

GS_003_SETBACK = GoldStandardFixture(
    fixture_id="GS-003",
    name="Parcel Setback 5m",
    vertices=[(5, 5), (95, 5), (95, 95), (5, 95)],
    expected_area_m2=8100.0,
)

GS_004_FAR = GoldStandardFixture(
    fixture_id="GS-004",
    name="FAR Benchmark",
    vertices=[(0, 0), (100, 0), (100, 100), (0, 100)],
    expected_area_m2=10000.0,
    expected_far=1.5,
)

GS_005_DENSITY = GoldStandardFixture(
    fixture_id="GS-005",
    name="Building Density Benchmark",
    vertices=[(0, 0), (100, 0), (100, 100), (0, 100)],
    expected_area_m2=10000.0,
    expected_density=0.20,
)
