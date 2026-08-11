"""Traceable Chinese drafting-assistance profiles.

The profiles in this module are deliberately *assistive*.  They organize
official references, layer families and machine-checkable expectations, but
they never claim that a DXF has passed statutory planning or drawing review.
Local planning conditions and the latest official text remain authoritative.
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class DraftingReference:
    code: str
    name: str
    authority: str
    status: str
    effective_date: str
    scope: str
    source_url: str
    note: str = ""


@dataclass(frozen=True)
class DraftingProfile:
    profile_id: str
    name: str
    description: str
    required_layers: Tuple[str, ...]
    recommended_layers: Tuple[str, ...]
    reference_codes: Tuple[str, ...]
    require_projected_crs_review: bool = False

    @property
    def all_layers(self) -> Tuple[str, ...]:
        return tuple(dict.fromkeys((*self.required_layers, *self.recommended_layers)))


_REFERENCES = (
    DraftingReference(
        code="GB/T 50001-2017",
        name="房屋建筑制图统一标准",
        authority="住房和城乡建设部",
        status="现行",
        effective_date="2018-05-01",
        scope="图幅、图线、字体、比例、尺寸标注和计算机辅助制图组织",
        source_url=(
            "https://ndls.org.cn/standard/index?"
            "a209=%E5%8C%97%E4%BA%AC%E7%90%86%E6%AD%A3%E8%BD%AF%E4%BB%B6"
            "%E8%82%A1%E4%BB%BD%E6%9C%89%E9%99%90%E5%85%AC%E5%8F%B8"
        ),
    ),
    DraftingReference(
        code="GB/T 50103-2010",
        name="总图制图标准",
        authority="住房和城乡建设部",
        status="使用前复核现行状态",
        effective_date="2011-03-01",
        scope="总平面图、道路、场地、管线和总图图例表达",
        source_url="https://www.mohurd.gov.cn/",
        note="软件只记录核对入口，不内置受地域和项目阶段影响的控制数值。",
    ),
    DraftingReference(
        code="GB/T 20257.1-2017",
        name="国家基本比例尺地图图式 第1部分：1:500 1:1000 1:2000地形图图式",
        authority="自然资源部",
        status="现行（2025年复审继续有效）",
        effective_date="2018-05-01",
        scope="1:500、1:1000、1:2000基础地形图符号和表达",
        source_url=(
            "https://std.samr.gov.cn/gb/search/gbDetailed?"
            "id=1ETOqX9v8pI%3D&mode=p"
        ),
    ),
    DraftingReference(
        code="MNR 2021 MUNICIPAL MAP (TRIAL)",
        name="市级国土空间总体规划制图规范（试行）",
        authority="自然资源部",
        status="试行",
        effective_date="2021-03-29",
        scope="市级国土空间总体规划图件、色彩、符号、数学基础和图幅配置",
        source_url=(
            "https://www.gov.cn/zhengce/zhengceku/2021-04/07/5598163/"
            "files/bd34c2bcbb6f467d8af880abc33f4c07.pdf"
        ),
    ),
    DraftingReference(
        code="MNR 2023 LAND-SEA CLASSIFICATION",
        name="国土空间调查、规划、用途管制用地用海分类指南",
        authority="自然资源部",
        status="正式施行",
        effective_date="2023-11-22",
        scope="国土空间用地用海分类名称、代码和使用层级",
        source_url=(
            "https://app.www.gov.cn/govdata/gov/202311/28/509752/article.html"
        ),
    ),
    DraftingReference(
        code="GB/T 39972-2021",
        name="国土空间规划“一张图”实施监督信息系统技术规范",
        authority="自然资源部",
        status="现行",
        effective_date="2021-10-01",
        scope="国土空间规划一张图数据组织和实施监督信息系统",
        source_url=(
            "https://std.samr.gov.cn/gb/search/gbDetailed?"
            "id=BD89DE8E08093D08E05397BE0A0A4FAD"
        ),
    ),
    DraftingReference(
        code="GB 50180-2018",
        name="城市居住区规划设计标准",
        authority="住房和城乡建设部",
        status="现行标准框架（正式项目逐条核对）",
        effective_date="2018-12-01",
        scope="居住区和居住街坊的规划结构、设施与空间环境",
        source_url="https://www.mohurd.gov.cn/",
    ),
)


_PROFILES = (
    DraftingProfile(
        profile_id="china_coursework_general",
        name="中国规划课程总平面（推荐）",
        description=(
            "面向城乡规划学生的总平面作业辅助模板；统一常用图层、图线和图面元素，"
            "不替代老师任务书或地方规划条件。"
        ),
        required_layers=(
            "PARCEL",
            "ROAD_REDLINE",
            "BUILDING",
            "GREEN",
            "ANNOTATION",
            "DIMENSION",
        ),
        recommended_layers=(
            "ROAD_CENTER",
            "ROAD_EDGE",
            "SETBACK",
            "PARKING",
            "ENTRANCE",
            "WATER",
            "TREE",
            "PARCEL_LABEL",
            "TITLE_BLOCK",
            "LEGEND",
            "NORTH_ARROW",
            "SCALE_BAR",
        ),
        reference_codes=(
            "GB/T 50001-2017",
            "GB/T 50103-2010",
            "GB/T 20257.1-2017",
        ),
    ),
    DraftingProfile(
        profile_id="china_residential_site",
        name="中国居住区总平面（学习辅助）",
        description=(
            "面向居住区总平面和课程设计，增加消防通行、停车、公共服务和景观图层；"
            "退线、间距、停车配比等仍须填写当地条件。"
        ),
        required_layers=(
            "PARCEL",
            "ROAD_REDLINE",
            "BUILDING",
            "GREEN",
            "FIRE_ACCESS",
            "ENTRANCE",
            "PARKING",
            "ANNOTATION",
            "DIMENSION",
        ),
        recommended_layers=(
            "ROAD_CENTER",
            "ROAD_EDGE",
            "SIDEWALK",
            "SETBACK",
            "EXISTING_BUILDING",
            "DEMOLITION",
            "PUBLIC_SERVICE",
            "MUNICIPAL_FACILITY",
            "WATER",
            "TREE",
            "LANDSCAPE",
            "PARCEL_LABEL",
            "TITLE_BLOCK",
            "LEGEND",
            "NORTH_ARROW",
            "SCALE_BAR",
        ),
        reference_codes=(
            "GB/T 50001-2017",
            "GB/T 50103-2010",
            "GB 50180-2018",
        ),
    ),
    DraftingProfile(
        profile_id="china_territorial_spatial_review",
        name="国土空间规划图件（试行规范辅助）",
        description=(
            "用于国土空间规划课程与图件整理，提供分类、控制线和基础地理图层；"
            "必须人工确认2000国家大地坐标系、高斯-克吕格投影及地方补充要求。"
        ),
        required_layers=(
            "ADMIN_BOUNDARY",
            "LAND_USE",
            "ECO_REDLINE",
            "PERMANENT_FARMLAND",
            "URBAN_DEVELOPMENT_BOUNDARY",
            "TRANSPORTATION",
            "WATER_SYSTEM",
            "ANNOTATION",
            "LEGEND",
            "NORTH_ARROW",
            "SCALE_BAR",
        ),
        recommended_layers=(
            "ROAD_REDLINE",
            "PUBLIC_SERVICE",
            "MUNICIPAL_FACILITY",
            "DISASTER_PREVENTION",
            "TERRAIN_CONTOUR",
            "ELEVATION",
            "TITLE_BLOCK",
            "GRID",
        ),
        reference_codes=(
            "MNR 2021 MUNICIPAL MAP (TRIAL)",
            "MNR 2023 LAND-SEA CLASSIFICATION",
            "GB/T 39972-2021",
            "GB/T 20257.1-2017",
        ),
        require_projected_crs_review=True,
    ),
)


def list_drafting_references() -> Tuple[DraftingReference, ...]:
    return _REFERENCES


def get_drafting_reference(code: str) -> DraftingReference:
    for reference in _REFERENCES:
        if reference.code == code:
            return reference
    raise KeyError(f"Unknown drafting reference: {code}")


def list_drafting_profiles() -> Tuple[DraftingProfile, ...]:
    return _PROFILES


def get_drafting_profile(profile_id: str) -> DraftingProfile:
    for profile in _PROFILES:
        if profile.profile_id == profile_id:
            return profile
    known = ", ".join(profile.profile_id for profile in _PROFILES)
    raise KeyError(f"Unknown drafting profile '{profile_id}'. Available: {known}")

