"""Planning Toolbox Windows 本地规划分析工作台 GUI 模块."""
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from planning_toolbox.gui.main_window import PlanningToolboxMainWindow

def main():
    """GUI 应用程序入口点。"""
    # 启用高 DPI 缩放支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Planning Toolbox 规划分析工作台")
    app.setOrganizationName("Planning Toolbox Team")

    window = PlanningToolboxMainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
