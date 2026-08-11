"""Package the bundled SketchUp importer as an installable RBZ archive."""

from __future__ import annotations

from pathlib import Path
import zipfile

from planning_toolbox.utils.file_integrity import sha256_file


ROOT_LOADER = "planning_toolbox_sketchup.rb"
SUPPORT_FOLDER = "planning_toolbox_sketchup"


def _plugin_source_dir() -> Path:
    path = Path(__file__).resolve().parent / "plugin"
    if not path.is_dir():
        raise FileNotFoundError("安装包缺少 SketchUp 插件资源，请重新安装 Planning Toolbox。")
    return path


def build_sketchup_extension(output_path: Path | str) -> dict[str, str | int]:
    """Build a deterministic, Extension Manager-compatible RBZ file."""
    output = Path(output_path).resolve()
    if output.suffix.lower() != ".rbz":
        raise ValueError("SketchUp 插件安装包必须使用 .rbz 扩展名。")
    source = _plugin_source_dir()
    loader = source / ROOT_LOADER
    support = source / SUPPORT_FOLDER
    if not loader.is_file() or not support.is_dir():
        raise FileNotFoundError("SketchUp 插件目录结构不完整，请重新安装 Planning Toolbox。")

    members = [loader, *sorted(path for path in support.rglob("*") if path.is_file())]
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for member in members:
            archive.write(member, member.relative_to(source).as_posix())

    with zipfile.ZipFile(output, "r") as archive:
        names = archive.namelist()
        archive.testzip()
    if ROOT_LOADER not in names or not any(name.startswith(f"{SUPPORT_FOLDER}/") for name in names):
        raise RuntimeError("生成的 SketchUp RBZ 结构校验失败。")
    return {
        "path": str(output),
        "sha256": sha256_file(output),
        "size_bytes": output.stat().st_size,
        "member_count": len(names),
    }


__all__ = ["ROOT_LOADER", "SUPPORT_FOLDER", "build_sketchup_extension"]
