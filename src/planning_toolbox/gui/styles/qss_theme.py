"""QSS 界面皮肤与视觉样式表 (Modern Dark Slate Theme for PySide6)."""

APP_QSS_THEME = """
/* 全局基础设置 */
QWidget {
    background-color: #1e1e24;
    color: #e0e0e6;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}

/* 主窗口卡片与容器 */
QFrame#ZoneFrame {
    background-color: #25252d;
    border: 1px solid #33333d;
    border-radius: 8px;
    padding: 10px;
}

QLabel#ZoneTitle {
    font-size: 15px;
    font-weight: bold;
    color: #4da6ff;
    padding-bottom: 4px;
}

/* 按钮样式 */
QPushButton {
    background-color: #2d313d;
    color: #ffffff;
    border: 1px solid #454958;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #3b3f4f;
    border-color: #5c6275;
}

QPushButton:pressed {
    background-color: #1d2028;
}

QPushButton:disabled {
    background-color: #1a1b22;
    color: #555560;
    border-color: #282933;
}

QPushButton#PrimaryButton {
    background-color: #0066cc;
    border-color: #0077eee;
    color: #ffffff;
    font-weight: bold;
    font-size: 14px;
    padding: 8px 18px;
}

QPushButton#PrimaryButton:hover {
    background-color: #0077ff;
}

QPushButton#PrimaryButton:disabled {
    background-color: #1a334d;
    color: #406080;
    border-color: #204060;
}

/* 输入框与下拉框 */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #18181c;
    color: #ffffff;
    border: 1px solid #383844;
    border-radius: 5px;
    padding: 5px 8px;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #0088ff;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

/* 选项卡 (QTabWidget) */
QTabWidget::pane {
    border: 1px solid #33333d;
    border-radius: 6px;
    background-color: #25252d;
}

QTabBar::tab {
    background-color: #1c1c22;
    color: #9999a6;
    border: 1px solid #2d2d38;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #25252d;
    color: #4da6ff;
    border-bottom-color: #25252d;
    font-weight: bold;
}

QTabBar::tab:hover:!selected {
    background-color: #282833;
    color: #cccccc;
}

/* 进度条 */
QProgressBar {
    background-color: #18181c;
    border: 1px solid #383844;
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-weight: bold;
}

QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0066cc, stop:1 #00ccff);
    border-radius: 5px;
}

/* 表格 (QTableWidget) */
QTableWidget {
    background-color: #1a1a20;
    border: 1px solid #33333d;
    gridline-color: #2a2a35;
    border-radius: 6px;
}

QHeaderView::section {
    background-color: #25252e;
    color: #4da6ff;
    padding: 6px;
    font-weight: bold;
    border: 1px solid #33333d;
}

/* 警告框与日志文本框 */
QTextEdit#LogTextEdit {
    background-color: #141418;
    color: #a0a0b0;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    border: 1px solid #2d2d38;
    border-radius: 5px;
}

/* 胶囊状态标签 */
QLabel#BadgeSuccess {
    background-color: #1b4728;
    color: #5cd68d;
    border: 1px solid #28663a;
    border-radius: 4px;
    padding: 2px 8px;
    font-weight: bold;
}

QLabel#BadgeWarning {
    background-color: #5c4314;
    color: #ffc866;
    border: 1px solid #805c1c;
    border-radius: 4px;
    padding: 2px 8px;
    font-weight: bold;
}

QLabel#BadgeError {
    background-color: #5c1c1c;
    color: #ff6666;
    border: 1px solid #802828;
    border-radius: 4px;
    padding: 2px 8px;
    font-weight: bold;
}
"""
