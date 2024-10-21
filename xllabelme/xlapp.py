# -*- coding: utf-8 -*-

import json
import os
import os.path as osp
import re
from statistics import mean
import time
import html

import numpy as np
import requests
import webbrowser

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QImage, QPixmap, QTransform
from PyQt5.QtWidgets import QApplication, QMenu, QAction, QFileDialog, QMessageBox, QActionGroup, QWidget

from pyxllib.prog.newbie import round_int
from pyxllib.prog.pupil import DictTool
from pyxllib.algo.geo import rect_bounds
from pyxllib.algo.shapelylib import ShapelyPolygon
from pyxllib.algo.pupil import make_index_function, ValuesStat, natural_sort_key
from pyxllib.file.specialist import XlPath
from pyxllib.cv.rgbfmt import RgbFormatter
from pyxllib.xlcv import xlcv
from pyxllib.ext.qt import show_message_box, WaitDialog
from pyxlpr.ai.clientlib import XlAiClient

from xllabelme import utils
from xllabelme.app import MainWindow
from xllabelme.label_file import LabelFile, LabelFileError
from xllabelme.shape import Shape
from xllabelme.widgets import LabelListWidgetItem

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
_COLORS[' '] = np.array((128, 128, 128), 'uint8')  # 空值强制映射为灰色


# 一些旧的项目配置，大概率用不上了，但留着以防万一
# '渊亭OCR':  # 这是比较旧的一套配置字段名
#     {'_attrs':
#          [['content_type', 1, 'str', ('印刷体', '手写体', '印章', '其它')],
#           ['content_kv', 1, 'str', ('key', 'value')],
#           ["content_class", 1, "str", ("姓名", "身份证号", "联系方式", "采样时间", "检测时间", "核酸结果", "其它类")],
#           ['text', 1, 'str'],
#           ],
#      'label_shape_color': 'content_class'.split(','),
#      'label_vertex_fill_color': 'content_kv'.split(','),
#      'default_label': json.dumps({'content_type': '印刷体', 'content_kv': 'value',
#                                   'content_class': '其它类', 'text': ''}, ensure_ascii=False),
#      },
# '核酸检测':  # 这是比较旧的一套配置字段名
#     {'_attrs':
#          [['text', 1, 'str'],
#           ["content_class", 1, "str", ("其它类", "姓名", "身份证号", "联系方式", "采样时间", "检测时间", "核酸结果")],
#           ['content_kv', 1, 'str', ('key', 'value')],
#           ],
#      'label_shape_color': 'content_class'.split(','),
#      'default_label': json.dumps({'text': '', 'content_class': '其它类', 'content_kv': 'value'}, ensure_ascii=False),
#      },
# '三码合一入学判定':
#     {'_attrs':
#          [['text', 1, 'str'],
#           ["category", 1, "str", ("姓名", "身份证", "联系方式", "采样时间", "检测时间", "核酸结果",
#                                   "14天经过或途经", "健康码颜色", "其他类")],
#           ['text_kv', 1, 'str', ('key', 'value')],
#           ],
#      'label_shape_color': 'category'.split(','),
#      'default_label': json.dumps({'text': '', 'category': '其他类', 'text_kv': 'value'}, ensure_ascii=False),
#      },
# 'XlCoco': {
#     '_attrs':
#         [['id', 1, 'int'],
#          ['text', 1, 'str'],  # 这个本来叫label，但为了规范，统一成text
#          ['category_id', 1, 'int'],
#          ['content_type', 1, 'str', ('印刷体', '手写体', '印章', '身份证', '表格', '其它证件类', '其它')],
#          ['content_class', 1, 'str'],
#          ['content_kv', 1, 'str', ('key', 'value')],
#          ['bbox', 0],
#          ['area', 0],
#          ['image_id', 0],
#          ['segmentation', 0],
#          ['iscrowd', 0],
#          ['points', 0, 'list'],
#          ['shape_color', 0, 'list'],
#          ['line_color', 0, 'list'],
#          ['vertex_color', 0, 'list'],
#          ],
#     'label_shape_color': 'category_id,content_class'.split(','),
#     'label_line_color': 'gt_category_id,gt_category_name'.split(','),
#     'label_vertex_fill_color': 'dt_category_id,dt_category_name,content_kv'.split(','),
# },
# 'Sroie2019+':
#     {'_attrs':
#          [['text', 1, 'str'],  # 原来叫label的，改成text
#           ['sroie_class', 1, 'str', ('other', 'company', 'address', 'date', 'total')],
#           ['sroie_kv', 1, 'str', ('other', 'key', 'value')],
#           ]
#      },


def q_pixmap_to_np_array(qpixmap):
    qimage = qpixmap.toImage()
    width, height = qimage.width(), qimage.height()
    channel_count = qimage.pixelFormat().channelCount()
    buffer = qimage.constBits().asarray(width * height * channel_count)
    np_array = np.frombuffer(buffer, dtype=np.uint8).reshape((height, width, channel_count))
    return np_array


def np_array_to_q_pixmap(np_array):
    if len(np_array.shape) == 2:
        height, width = np_array.shape
        channel_count = 1
    else:
        height, width, channel_count = np_array.shape
    bytes_per_line = channel_count * width

    if channel_count == 1:
        format = QImage.Format_Grayscale8
    elif channel_count == 3:
        format = QImage.Format_RGB888
    elif channel_count == 4:
        format = QImage.Format_RGBA8888
    else:
        raise ValueError("Unsupported channel count: {}".format(channel_count))

    qimage = QImage(np_array.data, width, height, bytes_per_line, format)
    return QPixmap.fromImage(qimage)


def __1_扩展的MainWindow():
    pass


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
        self.xlapi = None

        self.default_shape_color_mode = 0  # 用来设置不同的高亮检查格式，会从0不断自增。然后对已有配色方案轮循获取。
        self.image_root = None  # 图片所在目录。有特殊功能用途，用在json和图片没有放在同一个目录的情况。

        self.config_settings_menu()
        self.reset_project()

    def __1_基础功能(self):
        """ low-level级别的新增api """
        pass

    def 获取配置(self, name, default_value=None):
        st = self.settings
        if not st.contains(name):  # 如果没有配置，要先设置默认值
            if default_value:
                st.setValue(default_value)
            else:  # 否则这里有些常见参数，也有默认值。如果也不在这个预设里，就设置空字符串值。
                cfg = {'current_mode': '文字通用',
                       'auto_rec_text': False,
                       'language': 'zh_CN'}
                st.setValue(name, cfg.get(name, ''))
        v = st.value(name)
        maps = {'false': False, 'true': True}
        v = maps.get(v, v)
        return v

    def 设置配置(self, name, value):
        self.settings.setValue(name, value)

    def 查找控件(self, 名称, 类型=QWidget):
        return self.findChild(类型, 名称)

    def ____get_describe(self):
        """ 各种悬停的智能提示
        这块功能暂时不迁移到"原版labelme"中，毕竟也算是比较通用的
        """

    def get_pos_desc(self, pos, brief=False):
        """ 当前光标所在位置的提示

        :param pos: 相对原图尺寸、位置的坐标点

        光标位置、所在像素rgb值信息

        因为左下角的状态栏不支持富文本格式，所以一般光标信息是加到ToolTip
        """
        mainwin = self
        if not mainwin.imagePath:
            return ''

        # 1 坐标
        x, y = round(pos.x(), 2), round(pos.y(), 2)
        tip = f'pos(x={x}, y={y})'
        # 2 像素值
        shape_size = (0, 0, 0) if mainwin.arr_image is None else mainwin.arr_image.shape  # 要能兼容灰度图
        h, w = shape_size[:2]
        if 0 <= x < w - 1 and 0 <= y < h - 1:
            rgb = mainwin.arr_image[round_int(y), round_int(x)].tolist()  # 也有可能是rgba，就会有4个值
            if isinstance(rgb, int):
                rgb = [rgb] * 3
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
        mainwin = self
        if not mainwin.imagePath:
            return ''
        canvas = mainwin.canvas
        pixmap = canvas.pixmap
        # files_num = len(self.fileListWidget)
        filesize = XlPath(mainwin.imagePath).size(human_readable=True)
        shapes_num = len(mainwin.canvas.shapes)
        tip = f'本图信息：图片文件大小={filesize}, 高×宽={pixmap.height()}×{pixmap.width()}，' \
              f'形状数={shapes_num}'
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

    def __2_菜单类功能(self):
        pass

    def config_settings_menu(self):
        """ 菜单栏_设置 """

        def create_project_menu():
            # 定义一个回调函数
            def func(action):
                # 设置当前模式，并重置项目
                self.设置配置('current_mode', action.text())
                self.reset_project()

            # 创建一个名为"Project"的菜单，将其添加到settings_menu中
            project_menu = QMenu(self.tr('Project'), settings_menu)

            # 使用QActionGroup来实现互斥的actions
            action_group = QActionGroup(project_menu)

            # 添加actions到QActionGroup并链接到同一个插槽
            actions = []
            current_mode = self.获取配置('current_mode')
            projects = ['原版labelme', '增强版xllabelme',
                        'm2302中科院题库', 'm2303表格标注', 'm2303表格标注二阶段', 'm2305公式符号标注',
                        '文字通用', 'XlCoco']
            for mode in projects:
                # 创建QAction，设为可选中，并添加到action_group
                action = QAction(mode, action_group)
                action.setCheckable(True)
                actions.append(action)

                if mode == current_mode:
                    action.setChecked(True)

            # 将QActionGroup的触发信号连接到func
            action_group.triggered.connect(func)

            # 将QActionGroup添加到菜单中
            project_menu.addActions(action_group.actions())
            return project_menu

        def create_auto_rec_text_action():
            def func(x):
                self.设置配置('auto_rec_text', x)
                if x:
                    os.environ['XlAiAccounts'] = 'eyJwcml1IjogeyJ0b2tlbiI6ICJ4bGxhYmVsbWV5XipBOXlraiJ9fQ=='
                    try:
                        self.xlapi = XlAiClient()
                    except requests.exceptions.ConnectionError:
                        # 没有网络
                        self.xlapi = None
                        a.setChecked(False)
                        # 提示
                        show_message_box('尝试连接xmutpriu.com的api失败，请检查网络问题，比如关闭梯子。\n'
                                         '如果仍然连接不上，可能是服务器的问题，请联系"管理员"。',
                                         'xllabelme标注工具：连接自动识别的API失败')

            a = QAction(self.tr('自动识别(xlapi)'), settings_menu)
            a.setCheckable(True)
            if self.获取配置('auto_rec_text'):
                a.setChecked(True)
                func(True)
            else:
                a.setChecked(False)
            a.triggered.connect(func)
            return a

        def create_set_image_root_action():
            a = QAction(self.tr('Set pictures directory'), settings_menu)

            def func():
                self.image_root = XlPath(QFileDialog.getExistingDirectory(self.image_root))
                self.importDirImages(self.lastOpenDir)

            a.triggered.connect(func)
            return a

        def create_reset_config_action():
            a = QAction(self.tr('Restore default labelme configuration'), settings_menu)

            def func():
                (XlPath.home() / '.labelmerc').delete()
                msg_box = QMessageBox(QMessageBox.Information, "恢复labelme的默认配置",
                                      "注意，需要重启软件才能生效。")
                msg_box.setStandardButtons(QMessageBox.Ok)
                msg_box.exec_()

            a.triggered.connect(func)
            return a

        def create_savefile_without_dialog_action():
            a = utils.newAction(self,
                                self.tr("关闭保存标注文件的弹窗"),
                                lambda x: a.setChecked(x),
                                None,  # 快捷键
                                None,  # 图标
                                self.tr("无json标注文件情况下，保存时不启用dialog而是自动生成标注文件"),  # 左下角的提示
                                checkable=True,
                                checked=True,
                                )
            self.savefile_without_dialog_action = a
            return a

        settings_menu = self.menus.settings
        settings_menu.addMenu(create_project_menu())
        settings_menu.addSeparator()
        settings_menu.addAction(create_auto_rec_text_action())
        settings_menu.addAction(create_savefile_without_dialog_action())
        # 关闭该功能，发现原本就有类似的功能，是我重复造轮子了
        # settings_menu.addAction(create_set_image_root_action())
        settings_menu.addSeparator()
        settings_menu.addAction(create_reset_config_action())

    def __3_修改原版有的接口(self):
        """ 原版labelme有实现，但这里作了定制修改 """

    def saveLabels(self, filename):
        return self.project.saveLabels(filename)

    def __4_自己扩展的功能(self):
        """ high-level级别的新增api """

    def reset_project(self):
        """ 更新配置，切换到当前项目 """
        mode = self.获取配置('current_mode')
        if not hasattr(self, 'project'):
            self.project = eval(mode)(self)
            self.open_last_workspace()
        elif self.project.__class__.__name__ != mode:
            self.project.destroy()
            self.project = eval(mode)(self)
            self.open_last_workspace()

    def open_last_workspace(self):
        """ 打开上一次退出软件的工作空间状态 """
        # 如果保存了目录和文件，打开上次工作状态
        lastOpenDir, lastFileName = self.获取配置('lastOpenDir'), self.获取配置('lastFileName')
        if lastOpenDir:
            d = XlPath(lastOpenDir)
            if d.is_dir():
                if lastFileName:
                    p = d / lastFileName
                    if p.is_file():
                        self.importDirImages(d, filename=str(p), offset=0)
                        return
                self.importDirImages(d)


def __2_自定义项目():
    pass


class 原版labelme:
    """ 不同项目任务可以继承这个类，进行一些功能的定制
    这里设计默认是labelme原版功能
    """

    def __init__(self, mainwin):
        self.mainwin = mainwin
        mainwin.showMaximized()  # 窗口最大化
        self.菜单新增动作 = []
        self.create()

    def __1_基础功能(self):
        pass

    def 获取配置(self, name, default_value=None):
        return self.mainwin.获取配置(name, default_value)

    def 设置配置(self, name, value):
        self.mainwin.设置配置(name, value)

    def updateShape(self, shape, label_list_item=None):
        """
        :param shape:
        :param label_list_item: item是shape的父级，挂在labelList下的项目
        """
        mainwin = self.mainwin
        label_list_item = LabelListWidgetItem(shape.label, shape)
        hashtext = shape.label

        def parse_htext(htext):
            if htext and not mainwin.uniqLabelList.findItemsByLabel(htext):
                item = mainwin.uniqLabelList.createItemFromLabel(htext)
                mainwin.uniqLabelList.addItem(item)
                rgb = mainwin._get_rgb_by_label(htext)
                mainwin.uniqLabelList.setItemLabel(item, htext, rgb)
                return rgb
            elif htext:
                return mainwin._get_rgb_by_label(htext)
            else:
                return None

        parse_htext(hashtext)
        mainwin.labelDialog.addLabelHistory(hashtext)

        mainwin._update_shape_color(shape)

        return label_list_item

    def updateShapes(self, shapes):
        """ 自己扩展的

        输入新的带顺序的shapes集合，更新canvas和labelList相关配置
        """
        mainwin = self.mainwin
        mainwin.canvas.shapes = shapes
        mainwin.canvas.storeShapes()  # 备份形状

        # 不知道怎么insertItem，干脆全部清掉，重新画
        mainwin.labelList.clear()
        for sp in mainwin.canvas.shapes:
            label_list_item = self.updateShape(sp)
            mainwin.labelList.addItem(label_list_item)

    def set_label_color(self, label, color=None):
        """ 对普通文本值，做固定颜色映射 """
        if isinstance(color, str):
            color = RgbFormatter.from_name(color).to_tuple()
        self.mainwin.labelDialog.addLabelHistory(label)  # 文本加入检索
        # 主要为了兼容xllabelme的一个tolist操作，所以要转np
        _COLORS[label] = np.array(color, 'uint8')  # 颜色做固定映射
        _COLORS[str({'text': label})] = np.array(color, 'uint8')  # 被转成字典的时候，也要带颜色映射规则

    def updateLabelListItems(self):
        """ 更新所有的标注展示，一般是切换检查，重新设置颜色 """
        items = self.mainwin.labelList
        for i in range(len(items)):
            item = items[i]
            self.updateShape(item.shape(), item)

    def get_current_select_shape(self):
        """ 如果当前没有选中item（shape），会返回None """
        mainwin = self.mainwin
        if not mainwin.canvas.editing():
            return None, None
        item = mainwin.currentItem()
        if item is None:
            return None, None
        shape = item.shape()
        return item, shape

    def rec_text(self, points):
        """ 文字识别或者一些特殊的api接口 """
        # 识别指定的points区域
        if isinstance(points[0], QPointF):
            points = [(p.x(), p.y()) for p in points]
        im = xlcv.get_sub(self.mainwin.arr_image, points, warp_quad=True)

        texts, scores = [], []  # 因图片太小等各种原因，没有识别到结果，默认就设空值
        try:
            d = self.mainwin.xlapi.priu_api('basicGeneral', im)
            if 'shapes' in d:
                texts = [sp['label']['text'] for sp in d['shapes']]
                # scores = [sp['label']['score'] for sp in d['shapes']]
        except requests.exceptions.ConnectionError:
            pass

        text = ' '.join(texts)
        if scores:
            score = round(mean(scores), 4)
        else:
            score = -1

        # if score == -1:
        #     dprint(points, text, score, im.shape)

        return text, score

    def __2_菜单类功能(self):
        pass

    def 菜单添加动作(self, menu,
               text=None,  # 显示文本
               slot=None,  # 触发函数
               shortcut=None,  # 快捷键
               icon=None,  # 预设的图标
               tip=None,  # 详细提示内容
               checkable=False,  # 可勾选？
               enabled=True,  # 组件可使用？
               checked=False,  # 选中状态？
               name=None,  # 设一个全局名称，可以在其他地方需要的时候检索
               ):
        """ 通过这个函数添加的组会，切换project的时候，会自动进行检索销毁

        注意这里的menu不是QMenu对象，而是菜单功能清单，原理流程是
            1、提前用list存储到mainwin.actions里的动作列表，要展示的actions清单
            2、调用main.populateModeActions，可以把mainwin.acitons里的功能菜单都更新出来
            3、新建行为的时候，这个类里会做备份记录
            4、destroy自动销毁的时候，会用list.index进行检索把对应的action都移除
        """
        if text is None:
            self.菜单新增动作.append([menu, None])
            menu.append(None)
        else:
            action = utils.newAction(self.mainwin, self.mainwin.tr(text), slot,
                                     shortcut, icon, self.mainwin.tr(tip), checkable, enabled, checked)
            if name:
                action.setObjectName(name)
            self.菜单新增动作.append([menu, action])
            menu.append(action)
            return action

    def 菜单栏_编辑_添加动作(self, *args, **kwargs):
        return self.菜单添加动作(self.mainwin.actions.editMenu, *args, **kwargs)

    def 菜单栏_帮助_添加文档(self, 文档名称, 文档链接):
        return self.菜单添加动作(self.mainwin.actions.helpMenu, 文档名称, lambda: webbrowser.open(文档链接))

    def 左侧栏菜单添加动作(self, *args, **kwargs):
        return self.菜单添加动作(self.mainwin.actions.tool, *args, **kwargs)

    def 画布右键菜单添加动作(self, *args, **kwargs):
        return self.菜单添加动作(self.mainwin.actions.menu, *args, **kwargs)

    def 文件列表右键菜单添加动作(self, *args, **kwargs):
        return self.菜单添加动作(self.mainwin.actions.fileListMenu, *args, **kwargs)

    def create(self, update=True):
        """ 子类也可能调用这个方法，此时populateModeActions不需要提前执行 """
        mainwin = self.mainwin

        # 1 编辑菜单
        # 这个功能原labelme默认是开启的，导致兼职很容易经常误触增加多边形顶点，默认应该关闭
        self.菜单栏_编辑_添加动作()
        self.菜单栏_编辑_添加动作('统计标注数量', self.stat_shapes, tip='统计当前工作目录下，shapes框数等信息')
        self.菜单栏_编辑_添加动作('统计标注数量（完整版）', self.stat_shapes2,
                         tip='统计当前工作目录下，shapes框数等信息。'
                             '这是完整版，还会检查目录其他很多异常，可能会要非常久的时间。')
        self.菜单栏_编辑_添加动作()
        mainwin.add_point_to_edge_action = \
            self.菜单栏_编辑_添加动作('允许在多边形边上点击添加新顶点', checkable=True, tip='选中shape的edge时，增加分割点')
        mainwin.delete_selected_shape_with_warning_action = \
            self.菜单栏_编辑_添加动作('删除形状时会弹出提示框', checkable=True, checked=True, tip='选中shape的edge时，增加分割点')

        # 2 画布菜单
        self.画布右键菜单添加动作()
        mainwin.convert_to_rectangle_action = \
            self.画布右键菜单添加动作('将该多边形转为矩形', self.convert_to_rectangle, enabled=False)
        mainwin.split_shape_action = \
            self.画布右键菜单添加动作('切分该形状', self.split_shape, enabled=False,
                            tip='在当前鼠标点击位置，将一个shape拆成两个shape（注意，该功能会强制拆出两个矩形框）')
        self.画布右键菜单添加动作()
        self.画布右键菜单添加动作('旋转图片(往左翻⤿)', lambda: self.rotate_image(270),
                        tip='将图片和当前标注的形状，逆时针旋转90度(左翻)，可以多次操作调整到合适方向。'
                            '注意1：软件中操作并未改变原始图片，需要保存标注文件后，外部图片文件才会更新。'
                            '注意2：图片操作目前是撤销不了的，不过可以不保存再重新打开文件恢复初始状态。')
        self.画布右键菜单添加动作('旋转图片(往右翻⤾)', lambda: self.rotate_image(90),
                        tip='将图片和当前标注的形状，顺时针旋转90度(右翻)，可以多次操作调整到合适方向。'
                            '注意1：软件中操作并未改变原始图片，需要保存标注文件后，外部图片文件才会更新。'
                            '注意2：图片操作目前是撤销不了的，不过可以不保存再重新打开文件恢复初始状态。')
        # self.画布右键菜单添加动作('歪斜图片矫正', self.deskew_image,
        #                 tip='歪斜比较严重的图片，可以尝试使用该功能矫正。'
        #                     '注意1：软件中操作并未改变原始图片，需要保存标注文件后，外部图片文件才会更新。'
        #                     '注意2：图片操作目前是撤销不了的，不过可以不保存再重新打开文件恢复初始状态。')

        # + 更新菜单的显示
        if update:
            mainwin.populateModeActions()

    def destroy(self):
        """ 销毁项目相关配置 """
        for menu, action in list(reversed(self.菜单新增动作)):
            if action is not None:  # 如果 action 不是 None，那么从 menu 中移除它
                action.deleteLater()  # 这个好像不用显式执行，其他官方原本的action都没有执行，但执行下应该问题也不大
            for i in range(len(menu) - 1, -1, -1):
                if menu[i] is action:
                    menu.pop(i)
                    break
        self.菜单新增动作 = []  # 清空 菜单新增动作 列表

    def __3_修改原版有的接口(self):
        """ 原版labelme有实现，但这里作了定制修改 """

    def should_check_state_for_label_file(self, label_file):
        """ 根据标签文件决定是否设置复选框状态为已检查

        :param Path label_file: 标签文件的路径
        :return bool: 如果应设置为已检查则返回True，否则返回False
        """
        # return LabelFile.is_label_file(label_file)
        return XlPath(label_file).read_json()['shapes']

    def importDirImages(self, dirpath, pattern=None, load=True, filename=None, offset=1):
        QApplication.processEvents()

        mainwin = self.mainwin
        mainwin.actions.openNextImg.setEnabled(True)
        mainwin.actions.openPrevImg.setEnabled(True)

        if not mainwin.mayContinue() or not dirpath:
            return

        mainwin.lastOpenDir = dirpath
        mainwin.filename = filename
        mainwin.fileListWidget.clear()

        def read_labels(progress_callback):
            mainwin.loadedItems = []
            filenames = mainwin.scanAllImages(dirpath)
            n = len(filenames)
            for i, filename in enumerate(filenames, start=1):
                if pattern and pattern not in filename:
                    continue
                label_file = mainwin.get_label_path(filename)
                # 使用元组代替QListWidgetItem对象
                item = (filename, label_file.is_file() and self.should_check_state_for_label_file(label_file))
                mainwin.loadedItems.append(item)  # 存储项到列表中
                item_widget = QtWidgets.QListWidgetItem(filename)
                item_widget.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if item[1]:
                    item_widget.setCheckState(Qt.Checked)
                else:
                    item_widget.setCheckState(Qt.Unchecked)
                mainwin.fileListWidget.addItem(item_widget)
                progress_callback(int(i / n * 100))

        if pattern is None:  # 正常读取目录
            WaitDialog().run_with_progress(read_labels)
        else:  # TODO 只是检索目录下的文件
            for item in mainwin.loadedItems:  # 从存储的项中搜索
                if pattern in item[0]:  # 如果项的文本匹配到搜索的模式
                    item_widget = QtWidgets.QListWidgetItem(item[0])
                    item_widget.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    if item[1]:
                        item_widget.setCheckState(Qt.Checked)
                    else:
                        item_widget.setCheckState(Qt.Unchecked)
                    mainwin.fileListWidget.addItem(item_widget)  # 将匹配到的项添加到显示的列表中

        mainwin.openNextImg(load=load, offset=offset)

    def _get_rgb_by_label(self, label):
        mainwin = self.mainwin
        if mainwin._config["shape_color"] == "auto":
            item = mainwin.uniqLabelList.findItemByLabel(label)
            if item is None:
                item = mainwin.uniqLabelList.createItemFromLabel(label)
                mainwin.uniqLabelList.addItem(item)
                rgb = mainwin._get_rgb_by_label(label)
                mainwin.uniqLabelList.setItemLabel(item, label, rgb)
            label_id = mainwin.uniqLabelList.indexFromItem(item).row() + 1
            label_id += mainwin._config["shift_auto_shape_color"]
            return mainwin.LABEL_COLORMAP[label_id % len(mainwin.LABEL_COLORMAP)]
        elif (
                mainwin._config["shape_color"] == "manual"
                and mainwin._config["label_colors"]
                and label in mainwin._config["label_colors"]
        ):
            return mainwin._config["label_colors"][label]
        elif mainwin._config["default_shape_color"]:
            return mainwin._config["default_shape_color"]
        return (0, 255, 0)

    def editLabel(self, item=None):
        """ 编辑label时弹出的窗口 """
        mainwin = self.mainwin
        if item and not isinstance(item, LabelListWidgetItem):
            raise TypeError("item must be LabelListWidgetItem type")

        if not mainwin.canvas.editing():
            return
        if not item:
            item = mainwin.currentItem()
        if item is None:
            return
        shape = item.shape()
        if shape is None:
            return
        text, flags, group_id = mainwin.labelDialog.popUp(
            text=shape.label,
            flags=shape.flags,
            group_id=shape.group_id,
        )
        if text is None:
            return
        if not mainwin.validateLabel(text):
            mainwin.errorMessage(
                mainwin.tr("Invalid label"),
                mainwin.tr("Invalid label '{}' with validation type '{}'").format(
                    text, mainwin._config["validate_label"]
                ),
            )
            return
        shape.label = text
        shape.flags = flags
        shape.group_id = group_id

        mainwin._update_shape_color(shape)
        if shape.group_id is None:
            item.setText(
                '{} <font color="#{:02x}{:02x}{:02x}">●</font>'.format(
                    html.escape(shape.label), *shape.fill_color.getRgb()[:3]
                )
            )
        else:
            item.setText("{} ({})".format(html.escape(shape.label), shape.group_id))

        mainwin.setDirty()
        if mainwin.uniqLabelList.findItemByLabel(shape.label) is None:
            item = mainwin.uniqLabelList.createItemFromLabel(shape.label)
            mainwin.uniqLabelList.addItem(item)
            rgb = mainwin._get_rgb_by_label(shape.label)
            mainwin.uniqLabelList.setItemLabel(item, shape.label, rgb)

    def shapeSelectionChanged(self, n_selected):
        """ 遍历所有跟选中shape时会激活有关的Action动作 """
        mainwin = self.mainwin
        mainwin.convert_to_rectangle_action.setEnabled(n_selected)
        mainwin.split_shape_action.setEnabled(n_selected)

    def get_default_label(self, shape=None):
        """ 这个是自己自己扩展的一个获得默认文本值的功能 """
        return ''

    def newShape(self, text=None):
        """ 新建标注框时的规则
        """
        mainwin = self.mainwin
        items = mainwin.uniqLabelList.selectedItems()
        if items:
            text = items[0].data(Qt.UserRole)
        flags = {}
        group_id = None
        if mainwin._config["display_label_popup"]:
            previous_text = mainwin.labelDialog.edit.text()
            text, flags, group_id = mainwin.labelDialog.popUp(text)
            if not text:
                mainwin.labelDialog.edit.setText(previous_text)

        if text is None:
            text = self.get_default_label(shape=mainwin.canvas.shapes[-1])

        if text and not mainwin.validateLabel(text):
            mainwin.errorMessage(
                mainwin.tr("Invalid label"),
                mainwin.tr("Invalid label '{}' with validation type '{}'").format(
                    text, mainwin._config["validate_label"]
                ),
            )
            text = ""
        if text:
            mainwin.labelList.clearSelection()
            shape = mainwin.canvas.setLastLabel(text, flags)
            shape.group_id = group_id
            # shape.description = description
            mainwin.addLabel(shape)
            mainwin.actions.editMode.setEnabled(True)
            mainwin.actions.undoLastPoint.setEnabled(False)
            mainwin.actions.undo.setEnabled(True)
            mainwin.setDirty()
        else:
            mainwin.canvas.undoLastLine()
            mainwin.canvas.shapesBackups.pop()

    def addLabel(self, shape):
        mainwin = self.mainwin
        if shape.group_id is None:
            text = shape.label
        else:
            text = "{} ({})".format(shape.label, shape.group_id)
        label_list_item = LabelListWidgetItem(text, shape)
        mainwin.labelList.addItem(label_list_item)
        if mainwin.uniqLabelList.findItemByLabel(shape.label) is None:
            item = mainwin.uniqLabelList.createItemFromLabel(shape.label)
            mainwin.uniqLabelList.addItem(item)
            rgb = mainwin._get_rgb_by_label(shape.label)
            mainwin.uniqLabelList.setItemLabel(item, shape.label, rgb)
        mainwin.labelDialog.addLabelHistory(shape.label)
        for action in mainwin.actions.onShapesPresent:
            action.setEnabled(True)

        mainwin._update_shape_color(shape)
        label_list_item.setText(
            '{} <font color="#{:02x}{:02x}{:02x}">●</font>'.format(
                html.escape(text), *shape.fill_color.getRgb()[:3]
            )
        )

    def custom_format_shape(self, shape):
        """ 可以自定义存储回json时候的shape解析方式

        比如可以用于仅text字段的dict转成普通str
        存储的点集只保存两位小数等
        也可以用来进行一些后处理优化
        """
        s = shape
        data = s.other_data.copy()
        data.update(
            dict(
                label=s.label,
                points=[(round(p.x(), 2), round(p.y(), 2)) for p in s.points],  # 保存的点集数据精度不需要太高，两位小数足够了
                group_id=s.group_id,
                shape_type=s.shape_type,
                flags=s.flags,
            )
        )
        return data

    def saveLabels(self, filename):
        mainwin = self.mainwin
        lf = LabelFile()

        # 1 取出核心数据进行保存
        # shapes标注数据，用的是labelList里存储的item.shape()
        shapes = [self.custom_format_shape(item.shape()) for item in mainwin.labelList]
        flags = {}  # 每张图分类时，每个类别的标记，True或False
        # 整张图的分类标记
        for i in range(mainwin.flag_widget.count()):
            item = mainwin.flag_widget.item(i)
            key = item.text()
            flag = item.checkState() == Qt.Checked
            flags[key] = flag
        try:
            imagePath = osp.relpath(mainwin.imagePath, osp.dirname(filename))
            # 强制不保存 imageData
            imageData = mainwin.imageData if mainwin._config["store_data"] else None
            if osp.dirname(filename) and not osp.exists(osp.dirname(filename)):
                os.makedirs(osp.dirname(filename))
            lf.save(
                filename=filename,
                shapes=shapes,
                imagePath=imagePath,
                imageData=imageData,
                imageHeight=mainwin.image.height(),
                imageWidth=mainwin.image.width(),
                otherData=mainwin.otherData,
                flags=flags,
            )

            # 2 fileList里可能原本没有标记json文件的，现在可以标记
            mainwin.labelFile = lf
            items = mainwin.fileListWidget.findItems(
                mainwin.get_image_path2(mainwin.imagePath), Qt.MatchExactly
            )
            if len(items) > 0:
                if len(items) != 1:
                    raise RuntimeError("There are duplicate files.")
                items[0].setCheckState(Qt.Checked)
            # disable allows next and previous image to proceed
            # self.filename = filename
            return True
        except LabelFileError as e:
            mainwin.errorMessage(
                mainwin.tr("Error saving label data"), mainwin.tr("<b>%s</b>") % e
            )
            return False

    def __4_自己扩展的功能(self):
        """ high-level级别的新增api """

    def update_shape_text(self, shape, text=None):
        """ 更新text内容
        """
        if text is None:
            if self.获取配置('auto_rec_text') and self.mainwin.xlapi:
                text, _ = self.rec_text(shape.points)
        shape.label = text or ''
        return shape

    def split_shape(self):
        """ 将一个框拆成两个框

        TODO 支持对任意四边形的拆分
        策略1：现有交互机制上，选择参考点后，拆分出多边形
        策略2：出来一把剪刀，通过画线指定切分的详细形式
        """
        mainwin = self.mainwin
        item, shape = self.get_current_select_shape()
        if shape:
            # 1 获取两个shape
            # 第1个形状
            pts = [(p.x(), p.y()) for p in shape.points]
            l, t, r, b = rect_bounds(pts)
            p = mainwin.canvas.prevPoint.x()  # 光标点击的位置
            shape.shape_type = 'rectangle'
            shape.points = [QPointF(l, t), QPointF(p, b)]

            # 第2个形状
            shape2 = shape.copy()
            shape2.points = [QPointF(p, t), QPointF(r, b)]

            # 2 调整label
            # 如果开了识别模型，更新识别结果
            if self.获取配置('auto_rec_text') and mainwin.xlapi:
                self.update_shape_text(shape)
                self.update_shape_text(shape2)
            else:  # 否则按几何比例重分配文本
                from pyxlpr.data.imtextline import merge_labels_by_widths
                text = mainwin.get_labelattr(shape.label).get('text', '')
                text1, text2 = merge_labels_by_widths(list(text), [p - l, r - p], '')
                self.update_shape_text(shape, text1)
                self.update_shape_text(shape2, text2)

            # 3 更新到shapes里
            mainwin.canvas.selectedShapes.append(shape2)
            mainwin.addLabel(shape2)
            shapes = mainwin.canvas.shapes
            idx = shapes.index(shape)
            shapes = shapes[:idx + 1] + [shape2] + shapes[idx + 1:]  # 在相邻位置插入新的shape
            self.updateShapes(shapes)
            mainwin.setDirty()

    def convert_to_rectangle(self):
        """ 将shape形状改为四边形 """
        item, shape = self.get_current_select_shape()
        if shape:
            shape.shape_type = 'rectangle'
            pts = [(p.x(), p.y()) for p in shape.points]
            l, t, r, b = rect_bounds(pts)
            shape.points = [QPointF(l, t), QPointF(r, b)]
            self.updateShape(shape, item)
            self.mainwin.setDirty()

    def rotate_image(self, degree=90):
        """ 旋转图片，每次执行顺时针旋转90度 """

        def flip_points(sp, h):
            from pyxllib.algo.geo import resort_quad_points
            pts = sp.points
            if len(pts) < 2:  # 会有特殊情况，只有1个点的（m2305latex2lg）
                pts.append(pts[0])

            if sp.shape_type == 'rectangle':
                # 矩形要特殊处理，仍然确保第1个点在左上角
                x1, y1 = pts[0].x(), pts[0].y()
                x2, y2 = pts[1].x(), pts[1].y()

                pts[0].setX(h - y2)
                pts[0].setY(x1)
                pts[1].setX(h - y1)
                pts[1].setY(x2)
            elif sp.shape_type == 'polygon' and len(pts) == 4:
                pts = [[h - p.y(), p.x()] for p in pts]
                pts = resort_quad_points(pts)
                for p1, p2 in zip(sp.points, pts):
                    p1.setX(p2[0])
                    p1.setY(p2[1])
            else:  # 其他形状暂不特殊处理
                for point in sp.points:
                    x = point.x()  # 要中转存储下，不然等下x会被新值覆盖
                    point.setX(h - point.y())
                    point.setY(x)

        # 1 旋转shapes坐标
        mainwin = self.mainwin
        canvas = mainwin.canvas
        h = canvas.pixmap.height()
        shapes = canvas.shapes
        for sp in shapes:
            flip_points(sp, h)

        # 2 旋转图片
        self.updateShapes(shapes)
        transform = QTransform()
        transform.rotate(degree)
        canvas.pixmap = canvas.pixmap.transformed(transform)
        mainwin.image = canvas.pixmap.toImage()

        # 3 end
        canvas.repaint()
        mainwin.setDirty(3)

    def deskew_image(self):
        """ 歪斜图片矫正 """
        from pyxllib.xlcv import xlcv
        mainwin = self.mainwin
        canvas = mainwin.canvas
        image = q_pixmap_to_np_array(canvas.pixmap)
        image = xlcv.deskew_image(image)
        canvas.pixmap = np_array_to_q_pixmap(image)
        canvas.repaint()
        mainwin.setDirty(2)

    def move_file(self, dst=None):
        """ 把指定的文件移到其他目录、子目录里，可以参考 'm2303表格标注' 里的运用

        :param dst: 该参数可以不输入，默认移回当前工作目录
        """
        # 1 准备
        mainwin = self.mainwin
        item = mainwin.fileListWidget.currentItem()
        t = item.text()

        # 2 已经是分好类的，不处理
        if dst and t.startswith(dst + '/'):
            return
        elif not dst and '/' not in t:
            return

        # 3 目标目录
        if not mainwin.mayContinue():
            return  # 如果文件没保存，默认要保存后才能操作

        if dst:
            dst_path = XlPath.init(dst, mainwin.lastOpenDir)
        else:
            dst_path = XlPath(mainwin.lastOpenDir)
        dst_path.mkdir(parents=True, exist_ok=True)

        # 4 移动文件
        p = mainwin.get_image_path(t)
        p.move(dst_path / p.name)
        p2 = mainwin.get_label_path(t)
        p2.move(dst_path / p2.name, if_exists='skip')

        # 5 更新标签
        if dst:
            item.setText(dst + '/' + p.name)
        else:
            item.setText(p.name)
        self.mainwin.filename = dst_path / p.name

        # 6 要重新打开标注文件
        mainwin.openNextImg(_value=False, load=True, offset=0)

    def _stat_shape_base(self):
        def check_point_value(pts):
            for pt in pts:
                if max(pt) > 0:
                    return True
            return False

        def fmt(nums):
            t = ValuesStat(nums).summary(['g', '.2f', '.2f', 'g', 'g']).replace('\t', '  ')
            t = t.replace('总和', '框数')
            t = t.replace('总数', 'json文件数量')
            return t

        work_dir = XlPath(self.mainwin.lastOpenDir)
        msg = [f'统计当前工作目录里的信息：{work_dir.as_posix()}\n']

        msg.append('零、json中shapes数统计（标注框数）')
        files = list(work_dir.rglob_files('*.json'))
        nums, nums2 = [], []
        undo_files = []
        for f in files:
            data = f.read_json()
            shapes = data.get('shapes', [])
            shapes2 = [x for x in shapes if check_point_value(x['points'])]
            nums.append(len(shapes))
            nums2.append(len(shapes2))
            if len(shapes) != len(shapes2):
                undo_files.append(f.relpath(work_dir).as_posix())

        if sum(nums) == sum(nums2):
            msg.append(fmt(nums))
        else:
            msg.append('需标注' + fmt(nums))
            msg.append('已标注' + fmt(nums2))
            msg.append('未标完的文件如下：')
            msg += sorted(undo_files, key=natural_sort_key)
        msg.append('')

        return msg

    def stat_shapes(self):
        def func():
            work_dir = XlPath(self.mainwin.lastOpenDir)
            msg = self._stat_shape_base()
            msg.append(work_dir.check_size())
            return msg

        msg = WaitDialog(self.mainwin, '如果文件较多，需要一些时间，请稍等一会...').run(func)
        show_message_box('\n'.join(msg), '统计标注数量', copyable=True)

    def stat_shapes2(self):
        def func():
            work_dir = XlPath(self.mainwin.lastOpenDir)
            msg = ['功能解释文档：https://www.yuque.com/xlpr/pyxllib/check_summary'] + self._stat_shape_base()
            t = work_dir.check_summary()
            t = re.sub(r'【.*?】目录检查\s*', '', t)
            msg.append(t)
            return msg

        msg = WaitDialog(self.mainwin, '如果文件较多，需要一些时间，请稍等一会...').run(func)
        show_message_box('\n'.join(msg), '统计标注数量（完整版）', copyable=True)


class 增强版xllabelme(原版labelme):
    """ xllabelme扩展功能 """

    def __1_基础功能(self):
        pass

    def __init__(self, mainwin, _attrs=None, label_shape_colors=None):
        _attrs = _attrs or []
        self.label_shape_colors = label_shape_colors or ['text']

        self.attrs = self._attrs2attrs(_attrs)
        self.color_mode = 0
        self.keys = [x['key'] for x in self.attrs]
        self.hide_attrs = [x['key'] for x in self.attrs if x['show'] == 0]
        self.editable = False  # 原label是否可编辑
        self.keyidx = {x['key']: i for i, x in enumerate(self.attrs)}
        super(增强版xllabelme, self).__init__(mainwin)

    def _attrs2attrs(self, _attrs):
        """ 简化版的属性配置，转为标准版的属性配置 """
        res = []
        for x in _attrs:
            # 1 补长对齐
            if len(x) < 4:
                x += [None] * (4 - len(x))
            # 2 设置属性值
            d = {'key': x[0], 'show': x[1], 'type': x[2], 'items': x[3]}
            if isinstance(x[3], list):
                d['editable'] = 1
            res.append(d)
        return res

    def ____原XlLabel功能迁移到这(self):
        pass

    def parse_shape(self, shape):
        """ xllabelme相关扩展功能，常用的shape解析

        :return:
            showtext，需要重定制展示内容
            hashtext，用于哈希颜色计算的label
            labelattr，解析成字典的数据，如果其本身标注并不是字典，则该参数为空值
        """
        # 1 默认值，后面根据参数情况会自动调整
        showtext = shape.label
        labelattr = self.get_labelattr(shape.label)

        # 2 hashtext
        # self.hashtext成员函数只简单分析labelattr，作为shape_color需要扩展考虑更多特殊情况
        hashtext = self.get_hashtext(labelattr)
        # dprint(labelattr, hashtext)
        if not hashtext:
            if 'label' in labelattr:
                hashtext = labelattr['label']
            elif 'id' in labelattr:
                hashtext = labelattr['id']
            elif labelattr:
                hashtext = next(iter(labelattr.values()))
            else:
                hashtext = showtext
        hashtext = str(hashtext) or ' '  # 如果是空字符串，就映射到一个空格

        # 3 showtext
        if labelattr:
            # 3.1 隐藏部分属性
            showdict = {k: v for k, v in labelattr.items() if k not in self.hide_attrs}
            # 3.2 排序
            keys = sorted(showdict.keys(), key=make_index_function(self.keys))
            showdict = {k: showdict[k] for k in keys}
            showtext = json.dumps(showdict, ensure_ascii=False)
        # 3.3 转成文本，并判断是否有 group_id 待展示
        if shape.group_id not in (None, ''):  # 这里扩展支持空字符串
            showtext = "{} ({})".format(showtext, shape.group_id)

        # + return
        return showtext, hashtext, labelattr

    def get(self, k, default=None):
        idx = self.keyidx.get(k, None)
        if idx is not None:
            return self.attrs[idx]
        else:
            return default

    def __labelattr(self):
        """ label相关的操作

        labelme原始的格式，每个shape里的label字段存储的是一个str类型
        我为了扩展灵活性，在保留其str类型的前提下，存储的是一串可以解析为json字典的数据
        前者称为labelstr类型，后者称为labelattr格式

        下面封装了一些对label、labelattr进行操作的功能
        """

    def get_hashtext(self, labelattr, mode='label_shape_color'):
        """
        :param labelattr:
        :param mode:
            label_shape_color
            label_line_color
            label_vertex_fill_colorS
        :return:
            如果 labelattr 有对应key，action也有开，则返回拼凑的哈希字符串值
            否则返回 ''
        """
        ls = []

        if mode == 'label_shape_color':
            keys = self.label_shape_colors[self.color_mode]
        elif hasattr(self, mode):  # 其他模式暂时没有color_mode切换检查的概念
            keys = getattr(self, mode)
        else:
            keys = []

        for k in keys:
            if k in labelattr:
                ls.append(str(labelattr[k]) or ' ')
        if ls:
            return ', '.join(ls)
        else:
            return ''

    @classmethod
    def update_other_data(cls, shape):
        labelattr = cls.get_labelattr(shape.label, shape.other_data)
        if labelattr:
            shape.label = json.dumps(labelattr, ensure_ascii=False)
            shape.other_data = {}

    @classmethod
    def get_labelattr(cls, label, other_data=None):
        """ 如果不是字典，也自动升级为字典格式 """
        labelattr = DictTool.json_loads(label, 'text')
        if other_data:
            # 如果有扩展字段，则也将数据强制取入 labelattr
            labelattr.update(other_data)
        return labelattr

    @classmethod
    def set_label_attr(cls, label, k, v):
        """ 修改labelattr某项字典值 """
        labelattr = cls.get_labelattr(label)
        labelattr[k] = v
        return json.dumps(labelattr, ensure_ascii=False)

    def update_shape_text(self, x, text=None):
        """ 更新text内容

        :param x: 可以是shape结构，也可以是label字符串
            如果是shape结构，text又设为None，则会尝试用ocr模型识别文本
        """
        if isinstance(x, dict):
            if text is not None:
                x['text'] = text
        elif isinstance(x, str):
            if text is not None:
                x = self.set_label_attr(x, 'text', text)
        else:  # Shape结构
            if text is None:
                if self.获取配置('auto_rec_text') and self.mainwin.xlapi:
                    labelattr = self.get_labelattr(x.label)
                    labelattr['text'], labelattr['score'] = self.rec_text(x.points)
                    x.label = json.dumps(labelattr, ensure_ascii=False)
            else:
                x.label = self.set_label_attr(x.label, 'text', text)

        return x

    def __smart_label(self):
        """ 智能标注相关 """

    def __2_菜单类功能(self):
        pass

    def create(self, update=True):
        super().create(False)
        mainwin = self.mainwin

        self.左侧栏菜单添加动作()
        self.切换检查动作 = \
            self.左侧栏菜单添加动作('切换检查', self.switch_check_mode, 'F1',
                           tip='（快捷键：F1）切换不同的数据检查模式，有不同的高亮方案。')
        self.switch_check_mode(update=False)  # 把更精细的tip提示更新出来

        if update:
            mainwin.populateModeActions()

    def __3_修改原版有的接口(self):
        pass

    def _get_rgb_by_label(self, label):
        """ 该函数可以强制限定某些映射颜色 """
        if label in _COLORS:
            return _COLORS[label]

        mainwin = self.mainwin
        # 原来的颜色配置代码
        if mainwin._config["shape_color"] == "auto":
            try:
                item = mainwin.uniqLabelList.findItemsByLabel(label)[0]
                label_id = mainwin.uniqLabelList.indexFromItem(item).row() + 1
            except IndexError:
                label_id = 0
            label_id += mainwin._config["shift_auto_shape_color"]
            return mainwin.LABEL_COLORMAP[label_id % len(mainwin.LABEL_COLORMAP)]
        elif (
                mainwin._config["shape_color"] == "manual"
                and mainwin._config["label_colors"]
                and label in mainwin._config["label_colors"]
        ):
            return mainwin._config["label_colors"][label]
        elif mainwin._config["default_shape_color"]:
            return mainwin._config["default_shape_color"]

    def editLabel(self, item=None):
        mainwin = self.mainwin
        if item and not isinstance(item, LabelListWidgetItem):
            raise TypeError("item must be LabelListWidgetItem type")

        if not mainwin.canvas.editing():
            return
        if not item:
            item = mainwin.currentItem()
        if item is None:
            return
        shape = item.shape()
        if shape is None:
            return

        shape2 = mainwin.labelDialog.popUp2(shape, mainwin)
        if shape2 is None:
            return

        text, flags, group_id = shape2.label, shape2.flags, shape2.group_id

        if text is None:
            return
        if not mainwin.validateLabel(text):
            mainwin.errorMessage(
                mainwin.tr("Invalid label"),
                mainwin.tr("Invalid label '{}' with validation type '{}'").format(
                    text, mainwin._config["validate_label"]
                ),
            )
            return
        shape.label = text
        shape.flags = flags
        shape.group_id = group_id
        self.updateShape(shape, item)

        mainwin.setDirty()
        if not mainwin.uniqLabelList.findItemsByLabel(shape.label):
            item = QtWidgets.QListWidgetItem()
            item.setData(Qt.UserRole, shape.label)
            mainwin.uniqLabelList.addItem(item)

    def updateShape(self, shape, label_list_item=None):
        """
        :param shape:
        :param label_list_item: item是shape的父级，挂在labelList下的项目
        """
        mainwin = self.mainwin
        # 1 确定显示的文本 text
        self.update_other_data(shape)
        showtext, hashtext, labelattr = self.parse_shape(shape)
        if label_list_item:
            label_list_item.setText(showtext)
        else:
            label_list_item = LabelListWidgetItem(showtext, shape)

        # 2 保存label处理历史
        def parse_htext(htext):
            if htext and not mainwin.uniqLabelList.findItemsByLabel(htext):
                item = mainwin.uniqLabelList.createItemFromLabel(htext)
                mainwin.uniqLabelList.addItem(item)
                rgb = self._get_rgb_by_label(htext)
                mainwin.uniqLabelList.setItemLabel(item, htext, rgb)
                return rgb
            elif htext:
                return self._get_rgb_by_label(htext)
            else:
                return None

        parse_htext(hashtext)
        mainwin.labelDialog.addLabelHistory(hashtext)
        for action in mainwin.actions.onShapesPresent:
            action.setEnabled(True)

        # 3 定制颜色
        # 如果有定制颜色，则取用户设置的r, g, b作为shape颜色
        # 否则按照官方原版labelme的方式，通过label哈希设置
        hash_colors = self._get_rgb_by_label(hashtext)
        r, g, b = 0, 0, 0

        def seleter(key, default=None):
            if default is None:
                default = [r, g, b]

            if key in labelattr:
                v = labelattr[key]
            else:
                v = None

            if v:
                if len(v) == 3 and len(default) == 4:
                    # 如果默认值有透明通道，而设置的时候只写了rgb，没有写alpha通道，则增设默认的alpha透明度
                    v.append(default[-1])
                for i in range(len(v)):
                    if v[i] == -1:  # 用-1标记的位，表示用原始的hash映射值
                        v[i] = hash_colors[i]
                return v
            else:
                return default

        r, g, b = seleter('shape_color', hash_colors.tolist())[:3]
        label_list_item.setText(
            '{} <font color="#{:02x}{:02x}{:02x}">●</font>'.format(
                html.escape(showtext), r, g, b
            )
        )

        # 注意，只有用shape_color才能全局调整颜色，下面六个属性是单独调的
        # 线的颜色
        rgb_ = parse_htext(self.get_hashtext(labelattr, 'label_line_color'))
        shape.line_color = QtGui.QColor(*seleter('line_color', rgb_))
        # 顶点颜色
        rgb_ = parse_htext(self.get_hashtext(labelattr, 'label_vertex_fill_color'))
        shape.vertex_fill_color = QtGui.QColor(*seleter('vertex_fill_color', rgb_))
        # 悬停时顶点颜色
        shape.hvertex_fill_color = QtGui.QColor(*seleter('hvertex_fill_color', (255, 255, 255)))
        # 填充颜色
        shape.fill_color = QtGui.QColor(*seleter('fill_color', (r, g, b, 128)))
        # 选中时的线、填充颜色
        shape.select_line_color = QtGui.QColor(*seleter('select_line_color', (255, 255, 255)))
        shape.select_fill_color = QtGui.QColor(*seleter('select_fill_color', (r, g, b, 155)))

        return label_list_item

    def get_default_label(self, shape=None):
        mainwin = self.mainwin
        label = ''  # 这里可以设置默认label值
        if self.获取配置('auto_rec_text') and mainwin.xlapi and shape:
            k = 'label' if 'label' in self.keys else 'text'
            text, score = self.rec_text(shape.points)
            label = self.set_label_attr(label, k, text)
            label = self.set_label_attr(label, 'score', score)
        return label

    def newShape(self, text=None):
        """ 新建标注框时的规则
        """
        mainwin = self.mainwin
        items = mainwin.uniqLabelList.selectedItems()
        if items:
            text = items[0].data(Qt.UserRole)
        flags = {}
        group_id = None
        if mainwin._config["display_label_popup"]:
            previous_text = mainwin.labelDialog.edit.text()

            shape = Shape()
            shape.label = self.get_default_label(shape=mainwin.canvas.shapes[-1])
            shape = mainwin.labelDialog.popUp2(shape, mainwin)
            if shape is not None:
                text, flags, group_id = shape.label, shape.flags, shape.group_id

            if not text:
                mainwin.labelDialog.edit.setText(previous_text)

        if text is None:
            text = self.get_default_label(shape=mainwin.canvas.shapes[-1])

        if text and not mainwin.validateLabel(text):
            mainwin.errorMessage(
                mainwin.tr("Invalid label"),
                mainwin.tr("Invalid label '{}' with validation type '{}'").format(
                    text, mainwin._config["validate_label"]
                ),
            )
            text = ""
        if text:
            mainwin.labelList.clearSelection()
            shape = mainwin.canvas.setLastLabel(text, flags)
            shape.group_id = group_id
            mainwin.addLabel(shape)
            mainwin.actions.editMode.setEnabled(True)
            mainwin.actions.undoLastPoint.setEnabled(False)
            mainwin.actions.undo.setEnabled(True)
            mainwin.setDirty()
        else:
            mainwin.canvas.undoLastLine()
            mainwin.canvas.shapesBackups.pop()

    def addLabel(self, shape):
        """ 重载了官方的写法，这里这种写法才能兼容xllabelme的shape颜色渲染规则
        """
        label_list_item = self.updateShape(shape)
        self.mainwin.labelList.addItem(label_list_item)
        shape.other_data = {}

    def __4_自己扩展的功能(self):
        pass

    def switch_check_mode(self, *, update=True):
        """ 设置不同的高亮格式 """
        if update:
            self.color_mode = (self.color_mode + 1) % len(self.label_shape_colors)
            self.mainwin.reset_project()
            self.updateLabelListItems()

        # 提示给出更具体的使用的范式配置
        act = self.切换检查动作
        tip = act.toolTip()
        tip = re.sub(r'当前配置.*$', '', tip)
        tip += '当前配置：' + ', '.join(self.label_shape_colors[self.color_mode])
        act.setStatusTip(tip)
        act.setToolTip(tip)


class 文字通用(增强版xllabelme):

    def __1_基础功能(self):
        pass

    def __init__(self, mainwin):
        _attrs = [['text', 1, 'str'],
                  ['category', 1, 'str'],
                  ['text_kv', 1, 'str', ('other', 'key', 'value')],
                  ['text_type', 1, 'str', ('印刷体', '手写体', '其它')],
                  ]
        label_shape_colors = [['loc'],
                              ['symbo'],
                              ['symbo', 'loc'],
                              ]
        self.label_line_color = ['category']
        self.label_vertex_fill_color = ['text_kv']
        super(文字通用, self).__init__(mainwin, _attrs, label_shape_colors)

    def __3_修改原版有的接口(self):
        """ 原版labelme有实现，但这里作了定制修改 """

    def get_default_label(self, shape=None):
        d = {'text': '', 'category': '', 'text_kv': 'value', 'text_type': '印刷体'}
        return json.dumps(d, ensure_ascii=False)


class m2302中科院题库(增强版xllabelme):

    def __1_基础功能(self):
        pass

    def __init__(self, mainwin):
        _attrs = [['line_id', 1, 'int'],
                  ['content_type', 1, 'str', ('印刷体', '手写体')],
                  ["content_class", 1, "str", ("文本", "公式", "图片", "表格", "有机", "删除")],
                  ['text', 1, 'str'],
                  ]
        label_shape_colors = ['content_type,content_class'.split(','),
                              ['line_id'],
                              ]
        super(m2302中科院题库, self).__init__(mainwin, _attrs, label_shape_colors)

    def __2_菜单类功能(self):
        pass

    def create(self, update=True):
        super().create(False)
        mainwin = self.mainwin

        self.左侧栏菜单添加动作('标注排序', self.resort_shapes, tip='重新对目前标注的框进行排序')
        self.左侧栏菜单添加动作('检查全文章', self.browser_paper, tip='将内容按照shapes的顺序拼接成完整的文章，并检查公式渲染效果')
        self.左侧栏菜单添加动作('批量识别', self.batch_ocr, tip='将内容为__error__的shapes进行重新识别')
        # todo 检查文本行
        # todo 检查小分块

        if update:
            mainwin.populateModeActions()

    def __3_修改原版有的接口(self):
        """ 原版labelme有实现，但这里作了定制修改 """

    def get_default_label(self, shape=None):
        from pyxlpr.data.imtextline import TextlineShape

        # 1 获得基本内容。如果开了识别接口，要调api。
        mainwin = self.mainwin
        points = [(p.x(), p.y()) for p in shape.points]
        d = {'line_id': 1, 'content_type': '印刷体', 'content_class': '文本', 'text': ''}
        if mainwin.获取配置('auto_rec_text') and mainwin.xlapi and shape:
            # 识别指定的points区域
            im = xlcv.get_sub(mainwin.arr_image, points, warp_quad=True)
            try:
                d = mainwin.xlapi.priu_api('content_ocr', im, filename=str(mainwin.filename), timeout=5)
            # except requests.exceptions.ConnectionError:
            except Exception as e:
                d = {'line_id': 1, 'content_type': '印刷体', 'content_class': '文本', 'text': '__error__'}

        # 2 获得line_id
        line_id = 1
        shapes = mainwin.canvas.shapes  # 最后一个框
        if len(shapes) > 1:
            sp = shapes[-2]  # 当前框会变成shapes[-1]，所以要取shapes[-2]才是上一次建立的框
            line_id0 = json.loads(sp.label).get('line_id', 1)
            if TextlineShape(points).in_the_same_line(TextlineShape([(p.x(), p.y()) for p in sp.points])):
                line_id = line_id0
            else:
                line_id = line_id0 + 1
        d['line_id'] = line_id

        return json.dumps(d, ensure_ascii=False)

    def __4_自己扩展的功能(self):
        pass

    def resort_shapes(self):
        """ m2302中科院题库用，更新行号问题 """
        from pyxlpr.data.imtextline import TextlineShape

        mainwin = self.mainwin
        # 目前只用于一个项目
        if self.获取配置('current_mode') != 'm2302中科院题库':
            return

        # 0 数据预处理
        def parse(sp):
            points = [(p.x(), p.y()) for p in sp.points]
            return [sp, json.loads(sp.label), TextlineShape(points)]

        data = [parse(sp) for sp in mainwin.canvas.shapes]

        # 1 按照标记的line_id大小重排序
        # 先按行排序，然后行内按重心的x轴值排序（默认文本是从左往右读）。
        data.sort(key=lambda x: (x[1]['line_id'], x[2].centroid.x))

        # 2 编号重置，改成连续的自然数
        cur_line_id, last_tag = 0, ''
        for item in data:
            sp, label = item[0], item[1]
            if label['line_id'] != last_tag:
                cur_line_id += 1
                last_tag = label['line_id']
            label['line_id'] = cur_line_id
            sp.label = json.dumps(label, ensure_ascii=False)

        # 3 更新回数据
        self.updateShapes([x[0] for x in data])

    def browser_paper(self):
        """ 将当前标注的text内容拼接并在公式文章渲染网页打开 """
        # 1 拼接内容
        shapes = self.mainwin.canvas.shapes
        last_line_id = 1
        paper_text = []
        line_text = []
        for sp in shapes:
            label = json.loads(sp.label)
            if label['line_id'] != last_line_id:
                last_line_id = label['line_id']
                paper_text.append(' '.join(line_text))
                line_text = []

            if label['content_class'] == '公式':
                t = '$' + label['text'] + '$'
            else:
                t = label['text']
            line_text.append(t)

        paper_text.append(' '.join(line_text))
        content = '\n\n'.join(paper_text)

        # 2 获取渲染网页
        title = self.mainwin.get_label_path().stem
        r = requests.post('https://xmutpriu.com/latex/paper', json={'title': title, 'content': content})
        p = XlPath.init(title + '.html', XlPath.tempdir())
        p.write_text(r.text)
        webbrowser.open(p)

    def batch_ocr(self):
        """ 批量识别 """
        mainwin = self.mainwin
        # 目前只用于一个项目
        if self.获取配置('current_mode') != 'm2302中科院题库':
            return

        # 0 数据预处理
        def parse(sp):
            return [sp, json.loads(sp.label)]

        data = [parse(sp) for sp in mainwin.canvas.shapes]

        # 2 编号重置，改成连续的自然数
        for item in data:
            sp, label1 = item[0], item[1]
            if label1['text'] == '__error__':
                label2 = json.loads(self.get_default_label(sp))
                if label2['text'] != '__error__':
                    label2['line_id'] = label1['line_id']
                    sp.label = json.dumps(label2, ensure_ascii=False)

        # 3 更新回数据
        self.updateShapes([x[0] for x in data])


class m2303表格标注(原版labelme):

    def __2_菜单类功能(self):
        pass

    def create(self, update=True):
        super().create(False)
        mainwin = self.mainwin
        mainwin._config["display_label_popup"] = False  # 关闭这个参数可以在添加标注的时候不弹窗

        self.菜单栏_帮助_添加文档('表格标注文档', 'https://www.yuque.com/xlpr/data/zw58v08ay3rsy0hk?singleDoc#')

        self.文件列表右键菜单添加动作('移到"无表格"', lambda: self.move_file('无表格'))
        # self.文件列表右键菜单添加动作('移到"重复图"', lambda: self.move_file('重复图'))
        self.文件列表右键菜单添加动作('撤回目录', lambda: self.move_file('正常图'))

        # 3 canvas右键可以添加一个全图方框的标注
        self.画布右键菜单添加动作()
        self.画布右键菜单添加动作('全图标记一个表格矩形框', self.add_full_image_table_label,
                        tip='整张图都是一个完整的表格，全部画一个框')

        if update:
            mainwin.populateModeActions()  # 要运行下这个才会更新菜单

    def destroy(self):
        self.mainwin._config["display_label_popup"] = True
        super().destroy()

    def __3_修改原版有的接口(self):
        """ 原版labelme有实现，但这里作了定制修改 """

    def get_default_label(self, shape=None):
        return 'table'

    def __4_自己扩展的功能(self):
        pass

    def add_full_image_table_label(self):
        """ 这里有些底层操作想封装的，但一封装又失去了灵活性。有时候批量添加的时候，也不用每次都刷新
        想着就还是暂时先不封装
        """
        mainwin = self.mainwin
        shape = Shape('table', shape_type='polygon', flags={})
        # labelme的形状，下标是0开始，并且是左闭右闭的区间值
        h, w = mainwin.image.height() - 1, mainwin.image.width() - 1
        shape.points = [QPointF(*p) for p in [(0, 0), (w, 0), (w, h), (0, h)]]
        shape.close()
        mainwin.canvas.shapes.append(shape)
        mainwin.canvas.storeShapes()
        mainwin.canvas.update()
        mainwin.addLabel(shape)
        mainwin.actions.editMode.setEnabled(True)
        mainwin.actions.undoLastPoint.setEnabled(False)
        mainwin.setDirty()


class m2303表格标注二阶段(增强版xllabelme):

    def __1_基础功能(self):
        pass

    def __init__(self, mainwin):
        _attrs = [['text', 1, 'str', ('可见横线', '可见竖线', '不可见横线', '不可见竖线')],
                  ]
        label_shape_colors = [['text'],
                              ]
        super(m2303表格标注二阶段, self).__init__(mainwin, _attrs, label_shape_colors)

    def __2_菜单类功能(self):
        pass

    def create(self, update=True):
        super().create(False)

        mainwin = self.mainwin
        mainwin._config["display_label_popup"] = False  # 关闭这个参数可以在添加标注的时候不弹窗

        self.菜单栏_帮助_添加文档('表格二阶段标注说明', 'https://www.yuque.com/xlpr/data/kvq2g82zvk5x1lkb?singleDoc#')

        self.set_label_color('可见横线', (0, 123, 255))  # 蓝色
        self.set_label_color('可见竖线', (255, 0, 0))  # 红色
        self.set_label_color('不可见横线', (174, 223, 247))  # 不可见是可见对应的浅色
        self.set_label_color('不可见竖线', (255, 192, 203))

        self.文件列表右键菜单添加动作('移到"多表格"', lambda: self.move_file('多表格'))
        self.文件列表右键菜单添加动作('移到"复杂表"', lambda: self.move_file('复杂表'))
        self.文件列表右键菜单添加动作('移回"正常图"', lambda: self.move_file())

        if update:
            mainwin.populateModeActions()

    def destroy(self):
        self.mainwin._config["display_label_popup"] = True
        super().destroy()

    def __3_修改原版有的接口(self):
        """ 原版labelme有实现，但这里作了定制修改 """

    def get_default_label(self, shape=None):
        """ 还有些细节要调，如果弹窗，应该给出默认的几种类别文本 """
        # 0 注意：标注过程中，是可以修改框的位置的
        # shape.points = [QPointF(100, 100), QPointF(200, 200)]

        # 1 框的基本几何信息
        poly = ShapelyPolygon.gen([(p.x(), p.y()) for p in shape.points])
        bounds = poly.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]

        # 2 图片信息
        # 可见横线, 可见竖线, 不可见横线, 不可见竖线
        mainwin = self.mainwin
        points = [[p.x(), p.y()] for p in shape.points]
        # 为了避免拉出一条没有高度的矩形，做了点特殊处理
        points[1][0] = max(points[1][0], points[0][0] + 1)
        points[1][1] = max(points[1][1], points[0][1] + 1)

        im = xlcv.get_sub(mainwin.arr_image, points, warp_quad=True)
        im = xlcv.read(im, 0)  # 先转灰度图
        im = xlcv.replace_ground_color(im, 0, 255)  # 然后转白底黑字图
        color = im.mean()  # 计算平均颜色，越接近255，表示越是空白图。

        # 3 自动识别线类型
        visible_tag = '可见' if color < 250 else '不可见'
        line_tag = '竖线' if height > width else '横线'
        return json.dumps({'text': visible_tag + line_tag}, ensure_ascii=False)

    def custom_format_shape(self, shape):
        """ 可以自定义存储回json时候的shape解析方式（shape的序列化）

        比如可以用于仅text字段的dict转成普通str
        存储的点集只保存两位小数等
        也可以用来进行一些后处理优化
        """
        s = shape
        data = s.other_data.copy()
        data.update(
            dict(
                label=json.loads(s.label)['text'],
                points=[(round(p.x(), 2), round(p.y(), 2)) for p in s.points],  # 保存的点集数据精度不需要太高，两位小数足够了
                group_id=s.group_id,
                shape_type=s.shape_type,
                flags=s.flags,
            )
        )
        return data


class m2305公式符号标注(增强版xllabelme):

    def __1_基础功能(self):
        pass

    def __init__(self, mainwin):
        _attrs = []
        label_shape_colors = [['loc'],
                              ['symbo'],
                              ['symbo', 'loc'],
                              ]
        super(m2305公式符号标注, self).__init__(mainwin, _attrs, label_shape_colors)

    def __2_菜单类功能(self):
        pass

    def create(self, update=True):
        super().create(False)

        mainwin = self.mainwin
        self.菜单栏_帮助_添加文档('公式符号标注说明', 'https://www.yuque.com/xlpr/data/sn3uglc7g6l49akv?singleDoc#')

        self.左侧栏菜单添加动作('编辑latex', self.open_latex_webpage,
                       tip='打开本题原始latex代码网页，可以在网页修改代码错误后提交')
        self.左侧栏菜单添加动作('重置json', self.reset_json,
                       tip='从服务器下载新的json文件。注意，这会舍弃这张图原本标注的所有框')

        self.文件列表右键菜单添加动作('移到"错误图"', lambda: self.move_file('错误图'))
        self.文件列表右键菜单添加动作('移回"正常图"', lambda: self.move_file())

        if update:
            mainwin.populateModeActions()

    def __3_修改原版有的接口(self):
        """ 原版labelme有实现，但这里作了定制修改 """

    def should_check_state_for_label_file(self, label_file):
        """ 读取标注文件，看里面是否全部shape都含有位置信息了 """
        shapes = XlPath(label_file).read_json()['shapes']
        if not shapes:
            return False

        for sp in shapes:
            if sp['shape_type'] == 'rectangle':
                pts = [tuple(pt) for pt in sp['points']]
                if len(pts) < 2:
                    return False
                pt1, pt2 = pts[:2]
                if pt1 == pt2:
                    return False

        return True

    def newShape(self):
        """ 这个项目的newShape比较特别，并不实际添加shape，而是把无效的矩形框重新替换标注

        这个功能是有一定通用性的，以后可以考虑怎么加到一般功能性框架。
        """
        # 1 找到第一个未显示的shape
        mainwin = self.mainwin
        model = mainwin.labelList.model()
        for index in range(model.rowCount()):
            item = model.item(index, 0)
            if not item.checkState():
                break
        else:  # 如果已经全部修复，则创建不了新矩形
            return

        # 2 更新shapes位置
        shapes = mainwin.canvas.shapes

        mainwin.labelList.clearSelection()

        item.shape().points = shapes[-1].points
        item.shape().shape_type = shapes[-1].shape_type
        item.setCheckState(Qt.Checked)
        mainwin.canvas.shapes = shapes[:-1]

        mainwin.actions.editMode.setEnabled(True)
        mainwin.actions.undoLastPoint.setEnabled(False)
        mainwin.actions.undo.setEnabled(True)
        mainwin.setDirty()

    def saveLabels(self, filename):
        mainwin = self.mainwin
        lf = LabelFile()

        # 1 取出核心数据进行保存
        # shapes标注数据，用的是labelList里存储的item.shape()
        shapes = [self.custom_format_shape(item.shape()) for item in mainwin.labelList]
        flags = {}  # 每张图分类时，每个类别的标记，True或False
        # 整张图的分类标记
        for i in range(mainwin.flag_widget.count()):
            item = mainwin.flag_widget.item(i)
            key = item.text()
            flag = item.checkState() == Qt.Checked
            flags[key] = flag
        try:
            imagePath = osp.relpath(mainwin.imagePath, osp.dirname(filename))
            # 强制不保存 imageData
            imageData = mainwin.imageData if mainwin._config["store_data"] else None
            if osp.dirname(filename) and not osp.exists(osp.dirname(filename)):
                os.makedirs(osp.dirname(filename))
            lf.save(
                filename=filename,
                shapes=shapes,
                imagePath=imagePath,
                imageData=imageData,
                imageHeight=mainwin.image.height(),
                imageWidth=mainwin.image.width(),
                otherData=mainwin.otherData,
                flags=flags,
            )

            # 2 fileList里可能原本没有标记json文件的，现在可以标记
            mainwin.labelFile = lf
            items = mainwin.fileListWidget.findItems(
                mainwin.get_image_path2(mainwin.imagePath), Qt.MatchExactly
            )
            if len(items) > 0:
                if len(items) != 1:
                    raise RuntimeError("There are duplicate files.")
                if self.should_check_state_for_label_file(XlPath(filename)):
                    items[0].setCheckState(Qt.Checked)
            # disable allows next and previous image to proceed
            # self.filename = filename
            return True
        except LabelFileError as e:
            mainwin.errorMessage(
                mainwin.tr("Error saving label data"), mainwin.tr("<b>%s</b>") % e
            )
            return False

    def __4_自己扩展的功能(self):
        pass

    def open_latex_webpage(self):
        # todo 前端设计只展示单道题的页面？
        stem = self.mainwin.filename.stem
        webbrowser.open(f'https://xmutpriu.com/m2305latex2lg?findname={stem}')

    def reset_json(self):
        json_file = self.mainwin.get_label_path()
        response = requests.get(f'https://xmutpriu.com/m2305latex2lg/json/{json_file.stem}')
        json_file.write_text(response.text)
        self.mainwin.openNextImg(load=True, offset=0)
