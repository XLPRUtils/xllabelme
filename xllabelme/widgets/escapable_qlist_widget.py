from qtpy.QtCore import Qt
from qtpy import QtWidgets


class EscapableQListWidget(QtWidgets.QListWidget):
    """ 在用户按下Escape键时取消选择的所有项目 """
    def keyPressEvent(self, event):
        super(EscapableQListWidget, self).keyPressEvent(event)
        if event.key() == Qt.Key_Escape:
            self.clearSelection()
