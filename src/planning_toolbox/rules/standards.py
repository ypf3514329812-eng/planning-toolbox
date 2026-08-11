"""National-standard reference profiles for guided planning studies.

These profiles identify the standards that should be checked for a project
type. They intentionally do not invent universal numeric values: setbacks,
parking ratios, road widths, daylight requirements and similar controls may
also depend on the local plan, land-use conditions, building type and project
stage.
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class StandardReference:
    code: str
    name: str
    scope: str
    note: str


@dataclass(frozen=True)
class StandardsProfile:
    profile_id: str
    name: str
    description: str
    references: Tuple[StandardReference, ...]

    def __post_init__(self):
        if not self.profile_id.strip():
            raise ValueError("profile_id must not be empty")
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if not self.references:
            raise ValueError("a standards profile must have references")

    @property
    def reference_codes(self) -> Tuple[str, ...]:
        return tuple(reference.code for reference in self.references)

    def reference_summary(self) -> str:
        return "；".join(
            f"{reference.code}《{reference.name}》"
            for reference in self.references
        )


_PROFILES = (
    StandardsProfile(
        profile_id="custom_local",
        name="自定义/地方条件（推荐正式项目使用）",
        description="由用户输入项目所在地、规划条件和专项审查要求。",
        references=(
            StandardReference(
                "LOCAL",
                "项目所在地现行规划条件",
                "容积率、建筑密度、绿地率、退线、停车和道路条件",
                "必须以自然资源和规划主管部门出具的条件为准。",
            ),
        ),
    ),
    StandardsProfile(
        profile_id="residential_national_framework",
        name="居住区国家标准框架（学习辅助）",
        description="适用于居住区/居住街坊概念研究，不替代地方规划条件。",
        references=(
            StandardReference(
                "GB 50180-2018",
                "城市居住区规划设计标准",
                "居住区、居住街坊的规划结构、设施和空间环境",
                "其中标明的强制性条文必须逐条核对。",
            ),
            StandardReference(
                "GB 50137-2011",
                "城市用地分类与规划建设用地标准",
                "城乡用地分类和规划建设用地控制框架",
                "用于确认用地分类和规划层级，不直接产生项目退线值。",
            ),
            StandardReference(
                "GB 55031-2022",
                "民用建筑通用规范",
                "民用建筑基本空间与技术要求",
                "建筑专业设计阶段还需结合项目类型逐条核对。",
            ),
            StandardReference(
                "GB 55037-2022",
                "建筑防火通用规范",
                "建筑防火基本要求",
                "通道、消防和防火间距不能仅由概念道路图层代替。",
            ),
        ),
    ),
    StandardsProfile(
        profile_id="civil_building_national_framework",
        name="民用建筑国家标准框架（学习辅助）",
        description="适用于公共建筑和民用建筑前期布局研究。",
        references=(
            StandardReference(
                "GB 55031-2022",
                "民用建筑通用规范",
                "民用建筑的基本尺度和通用技术要求",
                "具体建筑类型还需执行相应项目规范。",
            ),
            StandardReference(
                "GB 55037-2022",
                "建筑防火通用规范",
                "建筑防火基本要求",
                "必须结合建筑高度、规模、功能和消防审查要求核对。",
            ),
            StandardReference(
                "GB 50352-2019",
                "民用建筑设计统一标准",
                "民用建筑设计通用原则和基本要求",
                "不替代专业建筑设计和施工图审查。",
            ),
        ),
    ),
)


def list_standards_profiles() -> tuple[StandardsProfile, ...]:
    return _PROFILES


def get_standards_profile(profile_id: str) -> StandardsProfile:
    for profile in _PROFILES:
        if profile.profile_id == profile_id:
            return profile
    known = ", ".join(profile.profile_id for profile in _PROFILES)
    raise KeyError(f"Unknown standards profile '{profile_id}'. Available: {known}")
