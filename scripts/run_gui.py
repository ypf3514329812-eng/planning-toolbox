"""一键启动 Planning Toolbox 本地规划分析工作台 GUI 界面。"""
import sys
from pathlib import Path

# 确保 src/ 目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from planning_toolbox.gui import main

if __name__ == "__main__":
    main()
