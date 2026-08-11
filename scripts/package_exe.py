"""Windows .exe 独立可执行程序打包工具。"""
import sys
import subprocess
from pathlib import Path

def package():
    spec_path = Path(__file__).resolve().parent.parent / "planning_toolbox.spec"
    print(f"[打包工具] 正在检查 PyInstaller 库...")
    try:
        import PyInstaller
    except ImportError:
        print("[提示] 当前未安装 PyInstaller。若要编译独立 .exe 文件，请先运行: pip install pyinstaller")
        raise SystemExit(1)

    print(f"[打包工具] 开始编译生成 Windows 独立可执行程序: {spec_path.name}")
    cmd = [sys.executable, "-m", "PyInstaller", str(spec_path), "--noconfirm"]
    res = subprocess.run(cmd)
    if res.returncode == 0:
        print("\n==========================================")
        print("   Windows .exe 独立程序打包完成！")
        print("==========================================")
        print(f"输出程序文件: dist/PlanningToolbox/PlanningToolbox.exe")
        print("请通过桌面快捷方式启动；目录版启动更快，也会避免每次双击重新解压大型依赖。")
        print("==========================================\n")
    else:
        print(f"[错误] 打包过程退出码: {res.returncode}")
        raise SystemExit(res.returncode or 1)

if __name__ == "__main__":
    package()
