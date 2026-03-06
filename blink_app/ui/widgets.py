from PySide6 import QtCore, QtGui, QtWidgets


class ToggleSwitch(QtWidgets.QCheckBox):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(52, 28)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.setCheckable(True)
        self.setText("")

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(52, 28)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        track_rect = QtCore.QRectF(1, 1, self.width() - 2, self.height() - 2)
        track_radius = track_rect.height() / 2
        knob_diameter = track_rect.height() - 6
        knob_y = track_rect.top() + 3
        if self.isChecked():
            knob_x = track_rect.right() - knob_diameter - 3
            track_color = QtGui.QColor("#4aa3ff")
            border_color = QtGui.QColor("#3f8fe0")
        else:
            knob_x = track_rect.left() + 3
            track_color = QtGui.QColor("#2b3142")
            border_color = QtGui.QColor("#3a4257")

        if not self.isEnabled():
            track_color = QtGui.QColor("#1d2332")
            border_color = QtGui.QColor("#242c3f")

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtGui.QPen(border_color, 1))
        painter.setBrush(QtGui.QBrush(track_color))
        painter.drawRoundedRect(track_rect, track_radius, track_radius)

        knob_rect = QtCore.QRectF(knob_x, knob_y, knob_diameter, knob_diameter)
        painter.setPen(QtGui.QPen(QtGui.QColor("#1d2332"), 1))
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#f6f7fb")))
        painter.drawEllipse(knob_rect)

        painter.end()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.toggle()
            event.accept()
            return

        super().mouseReleaseEvent(event)
