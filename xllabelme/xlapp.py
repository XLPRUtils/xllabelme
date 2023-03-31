# -*- coding: utf-8 -*-

import os
import os.path as osp

import numpy as np
from qtpy.QtCore import Qt
from qtpy import QtWidgets

from xllabelme import PY2
from xllabelme.label_file import LabelFile
from xllabelme.label_file import LabelFileError
from xllabelme.widgets import LabelListWidgetItem
from xllabelme.config.xllabellib import XlLabel

from xllabelme.app import MainWindow

from pyxllib.prog.newbie import round_int
from pyxllib.file.specialist import XlPath

from pyxllib.cv.rgbfmt import RgbFormatter

from pyxllib.algo.shapelylib import ShapelyPolygon

# ckz relabel2项目定制映射
_COLORS = {
    '印刷体': '鲜绿色',
    '手写体': '黄色',
    '印章': '红色',
    'old': '黑色'
}
_COLORS.update({'姓名': '黑色',
                '身份证': '黄色',
                '联系方式': '金色',
                '采样时间': '浅天蓝',
                '检测时间': '蓝色',
                '核酸结果': '红色',
                '14天经过或途经': '绿色',
                '健康码颜色': '鲜绿色',
                '其他类': '亮灰色'})

_COLORS = {k: np.array(RgbFormatter.from_name(v).to_tuple(), 'uint8') for k, v in _COLORS.items()}


class XlMainWindow(MainWindow):
    def __init__(
            self,
            config=None,
            filename=None,
            output=None,
            output_file=None,
            output_dir=None,
    ):
        super(XlMainWindow, self).__init__(config, filename, output, output_file, output_dir)
        self.arr_image = None  # cv2格式的图片
        self.xllabel = XlLabel(self)
        self.project = self.xllabel.open_project()
        self.open_last_workspace()

    def extendShapeMessage(self, shape):
        """ shape中自定义字段等信息

        :param shape: shape对象
        :return: 格式化的字符串内容
        """
        # 只考虑other_data中的数据
        datas = shape.other_data
        # 去掉扩展的颜色功能
        hides = {'shape_color', 'line_color', 'vertex_fill_color', 'hvertex_fill_color',
                 'fill_color', 'select_line_color', 'select_fill_color'}
        if self.label_hide_attrs.checked:
            hides |= {k for k in self.label_hide_attrs.value}
        keys = datas.keys() - hides
        msgs = [f'{k}={datas[k]}' for k in sorted(keys)]
        return ', '.join(msgs)

    def editLabel(self, item=None):
        if item and not isinstance(item, LabelListWidgetItem):
            raise TypeError("item must be LabelListWidgetItem type")

        if not self.canvas.editing():
            return
        if not item:
            item = self.currentItem()
        if item is None:
            return
        shape = item.shape()
        if shape is None:
            return

        shape2 = self.labelDialog.popUp2(shape, self)
        if shape2 is None:
            return

        text, flags, group_id = shape2.label, shape2.flags, shape2.group_id

        if text is None:
            return
        if not self.validateLabel(text):
            self.errorMessage(
                self.tr("Invalid label"),
                self.tr("Invalid label '{}' with validation type '{}'").format(
                    text, self._config["validate_label"]
                ),
            )
            return
        shape.label = text
        shape.flags = flags
        shape.group_id = group_id
        self.updateShape(shape, item)

        self.setDirty()
        if not self.uniqLabelList.findItemsByLabel(shape.label):
            item = QtWidgets.QListWidgetItem()
            item.setData(Qt.UserRole, shape.label)
            self.uniqLabelList.addItem(item)

    def addLabel(self, shape):
        """ 重载了官方的写法，这里这种写法才能兼容xllabelme的shape颜色渲染规则
        """
        label_list_item = self.updateShape(shape)
        self.labelList.addItem(label_list_item)
        shape.other_data = {}

    def updateShapes(self, shapes):
        """ 自己扩展的

        输入新的带顺序的shapes集合，更新canvas和labelList相关配置
        """
        self.canvas.shapes = shapes
        self.canvas.storeShapes()  # 备份形状

        # 不知道怎么insertItem，干脆全部清掉，重新画
        self.labelList.clear()
        for sp in self.canvas.shapes:
            label_list_item = self.updateShape(sp)
            self.labelList.addItem(label_list_item)

    def updateLabelListItems(self):
        for i in range(len(self.labelList)):
            item = self.labelList[i]
            self.updateShape(item.shape(), item)

    def updateShape(self, shape, label_list_item=None):
        return self.project.update_shape(shape, label_list_item)

    def _get_rgb_by_label(self, label):
        """ 该函数可以强制限定某些映射颜色 """
        if label in _COLORS:
            return _COLORS[label]

        # 原来的颜色配置代码
        if self._config["shape_color"] == "auto":
            try:
                item = self.uniqLabelList.findItemsByLabel(label)[0]
                label_id = self.uniqLabelList.indexFromItem(item).row() + 1
            except IndexError:
                label_id = 0
            label_id += self._config["shift_auto_shape_color"]
            return self.LABEL_COLORMAP[label_id % len(self.LABEL_COLORMAP)]
        elif (
                self._config["shape_color"] == "manual"
                and self._config["label_colors"]
                and label in self._config["label_colors"]
        ):
            return self._config["label_colors"][label]
        elif self._config["default_shape_color"]:
            return self._config["default_shape_color"]

    def saveLabels(self, filename):
        lf = LabelFile()

        # 1 取出核心数据进行保存
        def format_shape(s):
            data = s.other_data.copy()
            data.update(
                dict(
                    label=s.label.encode("utf-8") if PY2 else s.label,
                    points=[(round(p.x(), 2), round(p.y(), 2)) for p in s.points],  # 保存的点集数据精度不需要太高，两位小数足够了
                    group_id=s.group_id,
                    shape_type=s.shape_type,
                    flags=s.flags,
                )
            )
            return data

        # shapes标注数据，用的是labelList里存储的item.shape()
        shapes = [format_shape(item.shape()) for item in self.labelList]
        flags = {}  # 每张图分类时，每个类别的标记，True或False
        # 整张图的分类标记
        for i in range(self.flag_widget.count()):
            item = self.flag_widget.item(i)
            key = item.text()
            flag = item.checkState() == Qt.Checked
            flags[key] = flag
        try:
            imagePath = osp.relpath(self.imagePath, osp.dirname(filename))
            # 强制不保存 imageData
            imageData = self.imageData if self._config["store_data"] else None
            if osp.dirname(filename) and not osp.exists(osp.dirname(filename)):
                os.makedirs(osp.dirname(filename))
            lf.save(
                filename=filename,
                shapes=shapes,
                imagePath=imagePath,
                imageData=imageData,
                imageHeight=self.image.height(),
                imageWidth=self.image.width(),
                otherData=self.otherData,
                flags=flags,
            )

            # 2 fileList里可能原本没有标记json文件的，现在可以标记
            self.labelFile = lf
            items = self.fileListWidget.findItems(
                self.imagePath, Qt.MatchExactly
            )
            if len(items) > 0:
                if len(items) != 1:
                    raise RuntimeError("There are duplicate files.")
                items[0].setCheckState(Qt.Checked)
            # disable allows next and previous image to proceed
            # self.filename = filename
            return True
        except LabelFileError as e:
            self.errorMessage(
                self.tr("Error saving label data"), self.tr("<b>%s</b>") % e
            )
            return False

    @property
    def check_add_point_to_edge(self):
        """ 判断添加点到多边形edge上的功能是否有打开 """
        return self.add_point_to_edge_action.isChecked()

    def __get_describe(self):
        """ 各种悬停的智能提示 """

    def get_pos_desc(self, pos, brief=False):
        """ 当前光标所在位置的提示

        :param pos: 相对原图尺寸、位置的坐标点

        光标位置、所在像素rgb值信息

        因为左下角的状态栏不支持富文本格式，所以一般光标信息是加到ToolTip
        """
        if not self.imagePath:
            return ''

        # 1 坐标
        x, y = round(pos.x(), 2), round(pos.y(), 2)
        tip = f'pos(x={x}, y={y})'
        # 2 像素值
        h, w, _ = (0, 0, 0) if self.arr_image is None else self.arr_image.shape
        if 0 <= x < w - 1 and 0 <= y < h - 1:
            rgb = self.arr_image[round_int(y), round_int(x)].tolist()  # 也有可能是rgba，就会有4个值
            if brief:
                tip += f'，rgb={rgb}'
            else:
                color_dot = f'<font color="#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}">●</font>'
                tip += f'<br/>{color_dot}rgb={rgb}{color_dot}'
        return tip

    def get_image_desc(self):
        """ 鼠标停留在图片上时的提示内容，原始默认是Image

        这个一般是设置到状态栏展示
        """
        if not self.imagePath:
            return ''
        canvas = self.canvas
        pixmap = canvas.pixmap
        # files_num = len(self.fileListWidget)
        filesize = XlPath(self.imagePath).size(human_readable=True)
        shapes_num = len(self.canvas.shapes)
        tip = f'本图信息：图片文件大小={filesize}, height×width={pixmap.height()}×{pixmap.width()}，' \
              f'scale={canvas.scale:g}，shapes_num={shapes_num}'
        return tip

    def get_shape_desc(self, shape, pos):
        # 1 形状、坐标点（四舍五入保留整数值）
        tip = 'shape信息：' + shape.shape_type
        tip += ' ' + str([(round_int(p.x()), round_int(p.y())) for p in shape.points])
        # 2 如果有flags标记
        if shape.flags:
            tip += f'，{shape.flags}'
        # 3 增加个area面积信息
        poly = ShapelyPolygon.gen([(p.x(), p.y()) for p in shape.points])
        tip += f'，area={poly.area:.0f}'
        # + 坐标信息
        tip += f'；{self.get_pos_desc(pos, True)}'
        return tip

    def showMessage(self, text):
        """ setStatusBar只是设置值，而不是显示值
        显示值得用下述方式实现~~
        """
        self.statusBar().showMessage(text)

    def open_last_workspace(self):
        """ 打开上一次退出软件的工作空间状态 """
        # 如果保存了目录和文件，打开上次工作状态
        if 'lastOpenDir' in self.xllabel.meta_cfg:
            d = XlPath(self.xllabel.meta_cfg['lastOpenDir'])
            if d.is_dir():
                if 'filename' in self.xllabel.meta_cfg:
                    p = XlPath(self.xllabel.meta_cfg['filename'])
                    if p.is_file():
                        self.importDirImages(d, filename=str(p), offset=0)
                        return
                self.importDirImages(d)
