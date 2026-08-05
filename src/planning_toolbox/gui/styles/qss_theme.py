"""全高清高端暗黑玻璃工程主题 (Obsidian Glass & Neon Slate QSS Theme)."""

APP_QSS_THEME = """
/* 全局基础设置 */
QWidget {
    background-color: #0f1015;
    color: #e2e8f0;
    font-family: "Inter", "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
    selection-background-color: #3b82f6;
    selection-color: #ffffff;
}

/* 主窗口背景 */
QMainWindow {
    background-color: #0f1015;
}

/* 区域组卡片 (Zone Frames) */
QFrame#ZoneFrame {
    background-color: #171922;
    border: 1px solid #282b3a;
    border-radius: 10px;
    padding: 8px;
}

QLabel#ZoneTitle {
    font-size: 15px;
    font-weight: 700;
    color: #60a5fa;
    letter-spacing: 0.5px;
}

/* KPI 英雄数值卡片 (Hero Metric Cards) */
QFrame#KpiCard {
    background-color: #1e2230;
    border: 1px solid #333a4e;
    border-radius: 8px;
    padding: 8px 12px;
}

QLabel#KpiValue {
    font-size: 18px;
    font-weight: 800;
    color: #38bdf8;
}

QLabel#KpiLabel {
    font-size: 11px;
    color: #94a3b8;
    font-weight: 500;
}

/* 按钮基础样式 */
QPushButton {
    background-color: #242838;
    color: #f1f5f9;
    border: 1px solid #3d4358;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
    min-height: 24px;
}

QPushButton:hover {
    background-color: #32384e;
    border-color: #4f5773;
    color: #ffffff;
}

QPushButton:pressed {
    background-color: #1a1d29;
}

QPushButton:disabled {
    background-color: #141720;
    color: #475569;
    border-color: #1e2330;
}

/* 主要操作按钮 (Primary Run Button) */
QPushButton#PrimaryButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #0284c7);
    border: 1px solid #38bdf8;
    color: #ffffff;
    font-weight: 700;
    font-size: 14px;
    border-radius: 8px;
    padding: 10px 20px;
}

QPushButton#PrimaryButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #0369a1);
    border-color: #7dd3fc;
}

QPushButton#PrimaryButton:disabled {
    background: #1e293b;
    color: #64748b;
    border-color: #334155;
}

/* 快捷示例按钮 (Sample Loading Button) */
QPushButton#SampleButton {
    background-color: #1e293b;
    color: #38bdf8;
    border: 1px solid #0284c7;
    border-radius: 6px;
}

QPushButton#SampleButton:hover {
    background-color: #0369a1;
    color: #ffffff;
}

/* 输入框与下拉框 */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #12141c;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 5px 10px;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #38bdf8;
    background-color: #161923;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

/* 选项卡 (QTabWidget) */
QTabWidget::pane {
    border: 1px solid #282b3a;
    border-radius: 8px;
    background-color: #171922;
}

QTabBar::tab {
    background-color: #12141c;
    color: #94a3b8;
    border: 1px solid #232736;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 8px 18px;
    font-weight: 600;
    margin-right: 3px;
}

QTabBar::tab:selected {
    background-color: #171922;
    color: #38bdf8;
    border-bottom-color: #171922;
    font-weight: 700;
}

QTabBar::tab:hover:!selected {
    background-color: #1e2230;
    color: #cbd5e1;
}

/* 进度条 */
QProgressBar {
    background-color: #12141c;
    border: 1px solid #334155;
    border-radius: 6px;
    text-align: center;
    color: #f8fafc;
    font-weight: 700;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #06b6d4);
    border-radius: 5px;
}

/* 表格 (QTableWidget) */
QTableWidget {
    background-color: #12141c;
    border: 1px solid #282b3a;
    gridline-color: #232736;
    border-radius: 8px;
    font-size: 12px;
}

QHeaderView::section {
    background-color: #1a1d29;
    color: #38bdf8;
    padding: 7px;
    font-weight: 700;
    border: 1px solid #282b3a;
}

QTableWidget::item {
    padding: 4px;
}

QTableWidget::item:selected {
    background-color: #1e3a8a;
    color: #ffffff;
}

/* 控制台日志编辑框 */
QTextEdit#LogTextEdit {
    background-color: #0b0c10;
    color: #cbd5e1;
    font-family: "Fira Code", "Consolas", monospace;
    font-size: 12px;
    border: 1px solid #232736;
    border-radius: 6px;
    padding: 6px;
}

/* 状态彩带胶囊 (Pill Badges) */
QLabel#BadgeSuccess {
    background-color: #064e3b;
    color: #34d399;
    border: 1px solid #059669;
    border-radius: 12px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 11px;
}

QLabel#BadgeWarning {
    background-color: #451a03;
    color: #fbbf24;
    border: 1px solid #d97706;
    border-radius: 12px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 11px;
}

QLabel#BadgeError {
    background-color: #450a0a;
    color: #f87171;
    border: 1px solid #dc2626;
    border-radius: 12px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 11px;
}

QLabel#BadgeInfo {
    background-color: #172554;
    color: #60a5fa;
    border: 1px solid #2563eb;
    border-radius: 12px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 11px;
}
"""
