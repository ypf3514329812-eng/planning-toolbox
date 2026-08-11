"""Memory-friendly proxy for the Qt-native CAD preview."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class LazyCADPreviewCanvas(QWidget):
    """Create the heavyweight CAD preview only when it is actually needed.

    The rest of the workbench keeps automatic previews and PNG exports without
    loading the CAD parser while the window is idle.
    """

    preview_loaded = Signal()
    inspection_ready = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._preview: Optional[QWidget] = None
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._placeholder = QLabel("选择 DXF 后将在此生成 2D 矢量预览")
        self._placeholder.setObjectName("PreviewPlaceholder")
        self._placeholder.setWordWrap(True)
        self._placeholder.setStyleSheet(
            "color: #74766F; background: #F3F0E8; padding: 28px; "
            "border: 1px dashed #D0CBC0; border-radius: 8px;"
        )
        self._layout.addWidget(self._placeholder)

    @property
    def is_loaded(self) -> bool:
        return self._preview is not None

    def _ensure_preview(self):
        if self._preview is None:
            from planning_toolbox.gui.widgets.native_canvas_widget import NativeCADPreviewCanvas

            preview = NativeCADPreviewCanvas(self)
            preview.preview_loaded.connect(self.preview_loaded.emit)
            preview.inspection_ready.connect(self.inspection_ready.emit)
            self._layout.replaceWidget(self._placeholder, preview)
            self._placeholder.hide()
            self._preview = preview
        return self._preview

    def load_dxf_preview(
        self,
        dxf_path: Path | str,
        layer_config_path: Optional[Path | str] = None,
    ):
        self._ensure_preview().load_dxf_preview(dxf_path, layer_config_path)

    def clear_canvas(self, message: str = "等待加载 CAD DXF 图纸..."):
        if self._preview is None:
            self._placeholder.setText(message)
            return
        self._preview.clear_canvas(message)

    def cancel_preview(self, wait: bool = True) -> bool:
        if self._preview is None:
            return True
        return self._preview.cancel_preview(wait=wait)

    def fit_to_view(self):
        self._ensure_preview().fit_to_view()

    def save_png(self, path: Path | str, max_dimension: int = 2400) -> Path:
        return self._ensure_preview().save_png(path, max_dimension=max_dimension)

    @property
    def geometry_item_count(self) -> int:
        if self._preview is None:
            return 0
        return self._preview.geometry_item_count

    @property
    def figure(self) -> Any:
        return getattr(self._ensure_preview(), "figure", None)

    @property
    def ax(self) -> Any:
        return getattr(self._ensure_preview(), "ax", None)

    @property
    def canvas(self) -> Any:
        return getattr(self._ensure_preview(), "canvas", self._ensure_preview().view)
