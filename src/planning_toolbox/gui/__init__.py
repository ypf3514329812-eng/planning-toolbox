"""Planning Toolbox Windows 本地规划分析工作台 GUI 模块."""
import sys

from planning_toolbox.gui.single_instance import (
    acquire_single_instance,
    release_single_instance,
)

def main():
    """GUI 应用程序入口点。"""
    # Acquire the guard before importing Qt, matplotlib, image processing, or
    # CAD modules. A repeated double-click therefore exits without loading a
    # second 200+ MB workbench process.
    instance_handle = acquire_single_instance()
    if instance_handle is None:
        return 0

    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication

        from planning_toolbox.gui.main_window import PlanningToolboxMainWindow
        from planning_toolbox.gui.resources import gui_asset_path

        # 启用高 DPI 缩放支持
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

        app = QApplication(sys.argv)
        app.setApplicationName("Planning Toolbox 规划分析工作台")
        app.setOrganizationName("Planning Toolbox Team")
        icon_path = gui_asset_path("planning_toolbox.ico")
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))

        window = PlanningToolboxMainWindow()
        window.show()

        return app.exec()
    finally:
        release_single_instance(instance_handle)

if __name__ == "__main__":
    raise SystemExit(main())
