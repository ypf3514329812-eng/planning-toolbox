"""文件与输出目录选择区 (File Zone Widget)."""
from pathlib import Path
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog
)
from PySide6.QtCore import Signal

class FileZoneWidget(QFrame):
    """
    文件区：显示输入 DXF、输出目录、只读安全说明，提供文件与目录拾取按钮。
    """
    file_changed = Signal(str)          # DXF 文件切换信号
    output_dir_changed = Signal(str)    # 输出目录切换信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ZoneFrame")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        # 标题与安全声明
        top_bar = QHBoxLayout()
        title = QLabel("文件与输出位置 (Files & Workspace)")
        title.setObjectName("ZoneTitle")
        top_bar.addWidget(title)
        
        top_bar.addStretch()
        safety_notice = QLabel("🔒 原始 DXF 文件只读保护模式 (Zero-Mutation)")
        safety_notice.setStyleSheet("color: #70a0d0; font-size: 11px;")
        top_bar.addWidget(safety_notice)
        layout.addLayout(top_bar)

        # 1. 输入 DXF 文件行
        dxf_layout = QHBoxLayout()
        dxf_label = QLabel("输入 DXF 文件:")
        dxf_label.setFixedWidth(90)
        self.dxf_input = QLineEdit()
        self.dxf_input.setPlaceholderText("请选择或拖入 CAD DXF 文件 (*.dxf)...")
        self.dxf_input.textChanged.connect(self._on_dxf_text_changed)

        btn_browse_dxf = QPushButton("浏览 DXF...")
        btn_browse_dxf.clicked.connect(self._browse_dxf)

        btn_sample = QPushButton("⭐ 加载示例图纸")
        btn_sample.setToolTip("加载内置规划示例图纸 sample_data/sample_parcels.dxf 进行一键分析测试")
        btn_sample.clicked.connect(self._load_sample)

        self.lbl_status = QLabel("[未选择文件]")
        self.lbl_status.setObjectName("BadgeWarning")

        dxf_layout.addWidget(dxf_label)
        dxf_layout.addWidget(self.dxf_input)
        dxf_layout.addWidget(btn_browse_dxf)
        dxf_layout.addWidget(btn_sample)
        dxf_layout.addWidget(self.lbl_status)
        layout.addLayout(dxf_layout)

        # 2. 输出目录行
        out_layout = QHBoxLayout()
        out_label = QLabel("输出结果目录:")
        out_label.setFixedWidth(90)
        self.out_input = QLineEdit()
        self.out_input.setText(str(Path("output").resolve()))
        self.out_input.textChanged.connect(lambda t: self.output_dir_changed.emit(t))

        btn_browse_out = QPushButton("选择目录...")
        btn_browse_out.clicked.connect(self._browse_output_dir)

        out_layout.addWidget(out_label)
        out_layout.addWidget(self.out_input)
        out_layout.addWidget(btn_browse_out)
        layout.addLayout(out_layout)

    def _browse_dxf(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 CAD DXF 图纸文件", "", "AutoCAD DXF 文件 (*.dxf);;所有文件 (*.*)"
        )
        if file_path:
            self.dxf_input.setText(file_path)

    def _load_sample(self):
        sample_path = Path("sample_data/sample_parcels.dxf").resolve()
        if sample_path.exists():
            self.dxf_input.setText(str(sample_path))
        else:
            self.dxf_input.setText("sample_data/sample_parcels.dxf")

    def _browse_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出结果存储目录")
        if dir_path:
            self.out_input.setText(dir_path)

    def _on_dxf_text_changed(self, text: str):
        path = Path(text.strip())
        if text.strip() and path.exists() and path.suffix.lower() == ".dxf":
            self.lbl_status.setText("✓ 文件存在")
            self.lbl_status.setObjectName("BadgeSuccess")
        elif text.strip() and path.exists():
            self.lbl_status.setText("⚠ 非 DXF 文件")
            self.lbl_status.setObjectName("BadgeWarning")
        else:
            self.lbl_status.setText("✗ 文件不存在")
            self.lbl_status.setObjectName("BadgeError")
        
        self.lbl_status.setStyle(self.lbl_status.style())  # 刷新样式
        self.file_changed.emit(text.strip())

    def get_dxf_path(self) -> str:
        return self.dxf_input.text().strip()

    def get_output_dir(self) -> str:
        return self.out_input.text().strip()

    def set_dxf_path(self, path: str):
        self.dxf_input.setText(path)
