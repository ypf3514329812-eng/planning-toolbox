"""Low-saturation editorial light theme for the Planning Toolbox."""

APP_QSS_THEME = """
QWidget {
    background-color: #F1EEE6;
    color: #3C3D39;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
    selection-background-color: #B6C6D8;
    selection-color: #2F3B4A;
}
QMainWindow { background-color: #F1EEE6; }
QScrollArea#MainScrollArea { background-color: #F1EEE6; border: none; }
QWidget#MainContent { background-color: #F1EEE6; }
QSplitter::handle { background-color: #D8D3C8; }
QSplitter::handle:hover { background-color: #9AAFC4; }
QFrame#AppHeader {
    background-color: #F8F6F0;
    border: 1px solid #D8D3C8;
    border-radius: 12px;
}
QLabel#AppBrand { color: #566D8E; font-size: 17px; font-weight: 800; padding: 0; }
QLabel#AppSubtitle { color: #7B7D77; font-size: 10px; padding: 0; }
QPushButton#HeaderActionButton, QPushButton#HelpButton {
    min-width: 58px;
    min-height: 26px;
    padding: 6px 10px;
}
QPushButton#HeaderActionButton {
    background-color: #F6F3EC;
    color: #566D8E;
    border: 1px solid #C8C2B6;
    border-radius: 8px;
    font-weight: 700;
}
QPushButton#HeaderActionButton:hover { background-color: #E8E4DA; border-color: #8EA4BE; }
QPushButton#CompactHeaderButton {
    min-width: 30px;
    max-width: 30px;
    min-height: 26px;
    padding: 6px 4px;
    background-color: #F6F3EC;
    color: #566D8E;
    border: 1px solid #C8C2B6;
    border-radius: 8px;
    font-weight: 700;
}
QPushButton#CompactHeaderButton:hover { background-color: #E8E4DA; border-color: #8EA4BE; }
QPushButton#HelpButton {
    background-color: #E1EAF0;
    color: #566D8E;
    border: 1px solid #B1C4D3;
    border-radius: 9px;
    font-weight: 700;
}
QPushButton#HelpButton:hover { background-color: #D5E1E9; border-color: #8EA4BE; color: #3E536E; }
QPushButton#HelpButton:pressed { background-color: #C7D6E1; }
QDialog#HelpDialog { background-color: #F1EEE6; }
QDialog#WorkflowDialog { background-color: #F1EEE6; }
QLabel#WorkflowTitle { color: #566D8E; font-size: 20px; font-weight: 800; }
QLabel#WorkflowIntro { background-color: #E1EAF0; color: #4F667F; border: 1px solid #B1C4D3; border-radius: 8px; padding: 9px 12px; }
QLabel#WorkflowWorkingFile { color: #607A6A; font-weight: 700; padding: 2px 4px; }
QListWidget#WorkflowStageList { background-color: #F8F6F0; border: 1px solid #D8D3C8; border-radius: 10px; padding: 5px; }
QListWidget#WorkflowStageList::item { padding: 9px 8px; border-radius: 7px; }
QListWidget#WorkflowStageList::item:selected { background-color: #DCE6ED; color: #4F6683; font-weight: 700; }
QFrame#WorkflowDetail { background-color: #FFFDF9; border: 1px solid #D8D3C8; border-radius: 10px; }
QLabel#WorkflowStageTitle { color: #566D8E; font-size: 17px; font-weight: 800; }
QFrame#ContinuationBar { background-color: #E3EEE8; border: 1px solid #AAC6B5; border-radius: 9px; }
QLabel#ContinuationLabel { color: #557665; font-weight: 600; }
QLabel#HelpTitle { color: #566D8E; font-size: 20px; font-weight: 800; }
QLabel#HelpSubtitle { color: #74766F; font-size: 12px; }
QLabel#HelpIntro { background-color: #E1EAF0; color: #4F667F; border: 1px solid #B1C4D3; border-radius: 8px; padding: 9px 12px; }
QTextBrowser#HelpContent { background-color: #FFFDF9; color: #3C3D39; border: 1px solid #D8D3C8; border-radius: 9px; padding: 8px; }
QDialog#HelpDialog QTabWidget::pane { background-color: #FFFDF9; }
QDialog#HelpDialog QDialogButtonBox QPushButton { min-width: 80px; }
QFrame#ZoneFrame {
    background-color: #FBFAF6;
    border: 1px solid #D8D3C8;
    border-radius: 12px;
    padding: 2px;
}
QLabel#ZoneTitle {
    font-size: 15px;
    font-weight: 700;
    color: #566D8E;
    letter-spacing: 0.5px;
}
QFrame#KpiCard {
    background-color: #F6F3EC;
    border: 1px solid #D8D3C8;
    border-radius: 10px;
    padding: 2px;
}
QLabel#KpiValue { font-size: 18px; font-weight: 800; color: #607A6A; }
QLabel#KpiLabel { font-size: 11px; color: #74766F; font-weight: 600; }

QPushButton {
    background-color: #F6F3EC;
    color: #4A4C47;
    border: 1px solid #C8C2B6;
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 600;
    min-height: 24px;
}
QPushButton:hover { background-color: #E8E4DA; border-color: #9AAFC4; color: #3E536E; }
QPushButton:pressed { background-color: #DDD8CC; }
QPushButton:disabled { background-color: #EAE7DF; color: #A5A39B; border-color: #D8D3C8; }
QPushButton#PrimaryButton {
    background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0, stop: 0 #6F87A7, stop: 1 #8299B4);
    border: 1px solid #5D7699;
    color: #FFFFFF;
    font-weight: 700;
    font-size: 14px;
    border-radius: 9px;
    padding: 10px 20px;
}
QPushButton#PrimaryButton:hover {
    background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0, stop: 0 #5F789A, stop: 1 #748DAB);
    border-color: #536D8F;
}
QPushButton#PrimaryButton:disabled { background: #C9D2DC; color: #F7F8FA; border-color: #B8C4D1; }
QPushButton#SampleButton {
    background-color: #F0DDD6;
    color: #8E5F5A;
    border: 1px solid #D8AEA5;
    border-radius: 8px;
}
QPushButton#SampleButton:hover { background-color: #E6C6BE; color: #704D49; }

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #FFFFFF;
    color: #3C3D39;
    border: 1px solid #C8C2B6;
    border-radius: 8px;
    padding: 6px 10px;
    min-height: 30px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #8EA4BE;
    background-color: #FCFBF8;
}
QComboBox::drop-down { border: none; width: 24px; }
QLabel#NavLabel { color: #566D8E; font-weight: 700; font-size: 12px; }
QComboBox#TaskSelector {
    background-color: #EAF0F4;
    color: #4F6683;
    border: 1px solid #AFC1D0;
    border-radius: 9px;
    min-height: 34px;
    font-size: 13px;
    font-weight: 700;
    padding: 5px 12px;
}
QComboBox#TaskSelector:hover { background-color: #DFE9EF; border-color: #8EA4BE; }

QTabWidget::pane { border: 1px solid #D8D3C8; border-radius: 10px; background-color: #FBFAF6; }
QTabBar::tab {
    background-color: #EEEAE1;
    color: #74766F;
    border: 1px solid #D8D3C8;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
    padding: 8px 16px;
    font-weight: 600;
    margin-right: 3px;
}
QTabBar::tab:selected { background-color: #FBFAF6; color: #566D8E; border-bottom-color: #FBFAF6; font-weight: 700; }
QTabBar::tab:hover:!selected { background-color: #E5E1D7; color: #566D8E; }

QProgressBar {
    background-color: #E7E3DA;
    border: 1px solid #D0CBC0;
    border-radius: 7px;
    text-align: center;
    color: #4A4C47;
    font-weight: 700;
}
QProgressBar::chunk {
    background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0, stop: 0 #829A8B, stop: 1 #7189AA);
    border-radius: 6px;
}
QTableWidget {
    background-color: #FFFDF9;
    alternate-background-color: #F6F3EC;
    border: 1px solid #D8D3C8;
    gridline-color: #E2DED5;
    border-radius: 9px;
    font-size: 12px;
}
QHeaderView::section {
    background-color: #E8E4DA;
    color: #566D8E;
    padding: 7px;
    font-weight: 700;
    border: 1px solid #D8D3C8;
}
QTableWidget::item { padding: 4px; }
QTableWidget::item:selected { background-color: #B9C8D9; color: #2F3B4A; }

QTextEdit#LogTextEdit {
    background-color: #F6F3EC;
    color: #50534D;
    font-family: "Consolas", "Microsoft YaHei", sans-serif;
    font-size: 12px;
    border: 1px solid #D8D3C8;
    border-radius: 8px;
    padding: 6px;
}
QLabel#BadgeSuccess { background-color: #E3EEE8; color: #557665; border: 1px solid #AAC6B5; border-radius: 12px; padding: 3px 10px; font-weight: 700; font-size: 11px; }
QLabel#BadgeWarning { background-color: #F4E9D3; color: #8B6B3F; border: 1px solid #D8B781; border-radius: 12px; padding: 3px 10px; font-weight: 700; font-size: 11px; }
QLabel#BadgeError { background-color: #F4DDDA; color: #9B5C57; border: 1px solid #D6A19A; border-radius: 12px; padding: 3px 10px; font-weight: 700; font-size: 11px; }
QLabel#BadgeInfo { background-color: #E1EAF0; color: #5F7892; border: 1px solid #B1C4D3; border-radius: 12px; padding: 3px 10px; font-weight: 700; font-size: 11px; }
QToolTip { background-color: #3E4C5D; color: #FFFFFF; border: 1px solid #6F87A7; padding: 5px; }
QScrollBar:vertical { background: #ECE8DF; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #C2C7C2; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #9AAFC4; }
QScrollBar:horizontal { background: #ECE8DF; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #C2C7C2; border-radius: 5px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #9AAFC4; }
"""
