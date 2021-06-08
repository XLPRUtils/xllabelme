# -*- encoding: utf-8 -*-

from xllabelme.widgets import LabelListWidget
from xllabelme.widgets import LabelListWidgetItem


def test_LabelListWidget(qtbot):
    widget = LabelListWidget()

    item = LabelListWidgetItem(text="person <font color='red'>●</fon>")
    widget.addItem(item)
    item = LabelListWidgetItem(text="dog <font color='blue'>●</fon>")
    widget.addItem(item)

    widget.show()
    qtbot.addWidget(widget)
    qtbot.waitForWindowShown(widget)
