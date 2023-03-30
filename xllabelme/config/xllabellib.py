import json
import os
import os.path as osp
import time
import re
from statistics import mean

import requests

from PyQt5.QtCore import QPointF
from PyQt5.QtWidgets import QMenu, QAction, QFileDialog, QMessageBox
from qtpy import QtGui
from qtpy.QtCore import Qt

from pyxllib.file.specialist import XlPath
from pyxllib.algo.geo import rect_bounds
from pyxllib.algo.pupil import make_index_function
from pyxllib.prog.pupil import DictTool
from pyxlpr.ai.clientlib import XlAiClient
from pyxllib.algo.shapelylib import ShapelyPolygon

from xllabelme import utils
from xllabelme.widgets import LabelListWidgetItem
from xllabelme.shape import Shape

_CONFIGS = {
    '原版labelme': {},
    'xllabelme': {},
    'm2302中科院题库':  # 这是比较旧的一套配置字段名
        {'_attrs':
             [['line_id', 1, 'int'],
              ['content_type', 1, 'str', ('印刷体', '手写体')],
              ["content_class", 1, "str", ("文本", "公式", "图片", "表格")],
              ['text', 1, 'str'],
              ],
         'label_shape_color': 'content_type,content_class'.split(','),
         'label_shape_color2': ['line_id'],
         'default_label': json.dumps({'line_id': 1,
                                      'content_type': '印刷体',
                                      'content_class': '文本',
                                      'text': ''}, ensure_ascii=False),
         },
    'm2303表格标注': {},
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
    '文字通用':
        {'_attrs':
             [['text', 1, 'str'],
              ['category', 1, 'str'],
              ['text_kv', 1, 'str', ('other', 'key', 'value')],
              ['text_type', 1, 'str', ('印刷体', '手写体', '其它')],
              ],
         'label_line_color': ['category'],
         'label_vertex_fill_color': ['text_kv']
         },
    'XlCoco': {
        '_attrs':
            [['id', 1, 'int'],
             ['text', 1, 'str'],  # 这个本来叫label，但为了规范，统一成text
             ['category_id', 1, 'int'],
             ['content_type', 1, 'str', ('印刷体', '手写体', '印章', '身份证', '表格', '其它证件类', '其它')],
             ['content_class', 1, 'str'],
             ['content_kv', 1, 'str', ('key', 'value')],
             ['bbox', 0],
             ['area', 0],
             ['image_id', 0],
             ['segmentation', 0],
             ['iscrowd', 0],
             ['points', 0, 'list'],
             ['shape_color', 0, 'list'],
             ['line_color', 0, 'list'],
             ['vertex_color', 0, 'list'],
             ],
        'label_shape_color': 'category_id,content_class'.split(','),
        'label_line_color': 'gt_category_id,gt_category_name'.split(','),
        'label_vertex_fill_color': 'dt_category_id,dt_category_name,content_kv'.split(','),
    },
    # 'Sroie2019+':
    #     {'_attrs':
    #          [['text', 1, 'str'],  # 原来叫label的，改成text
    #           ['sroie_class', 1, 'str', ('other', 'company', 'address', 'date', 'total')],
    #           ['sroie_kv', 1, 'str', ('other', 'key', 'value')],
    #           ]
    #      },
}


def __1_自定义项目():
    pass


class 原版labelme:
    """ 不同项目任务可以继承这个类，进行一些功能的定制
    这里设计默认是labelme原版功能
    """

    def __init__(self, mainwin):
        self.mainwin = mainwin
        self.xllabel = mainwin.xllabel

    def destroy(self):
        """ 销毁项目相关配置 """
        pass

    def update_shape(self, shape, label_list_item=None):
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

    def new_shape(self):
        """Pop-up and give focus to the label editor.

        position MUST be in global coordinates.
        """
        mainwin = self.mainwin
        items = mainwin.uniqLabelList.selectedItems()
        text = None
        if items:
            text = items[0].data(Qt.UserRole)
        flags = {}
        group_id = None
        if mainwin._config["display_label_popup"] or not text:
            previous_text = mainwin.labelDialog.edit.text()

            text = self.get_default_label(shape=mainwin.canvas.shapes[-1])
            text, flags, group_id = mainwin.labelDialog.popUp(text)

            if not text:
                mainwin.labelDialog.edit.setText(previous_text)

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

    def get_default_label(self, shape=None):
        """ 新建框的时候，使用的默认label值

        在这里可以定制不同项目生成新标注框的规则
        这里有办法获取原图，也有办法获取标注的shape，从而可以智能推断，给出识别值的
        """
        return self.mainwin.labelDialog.edit.text()


class xllabelme(原版labelme):
    """ xllabelme扩展功能 """

    def __init__(self, mainwin):
        super().__init__(mainwin)
        self.xllabel = mainwin.xllabel

    def update_shape(self, shape, label_list_item=None):
        """
        :param shape:
        :param label_list_item: item是shape的父级，挂在labelList下的项目
        """
        mainwin = self.mainwin
        # 1 确定显示的文本 text
        self.xllabel.update_other_data(shape)
        showtext, hashtext, labelattr = self.xllabel.parse_shape(shape)
        if label_list_item:
            label_list_item.setText(showtext)
        else:
            label_list_item = LabelListWidgetItem(showtext, shape)

        # 2 保存label处理历史
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
        for action in mainwin.actions.onShapesPresent:
            action.setEnabled(True)

        # 3 定制颜色
        # 如果有定制颜色，则取用户设置的r, g, b作为shape颜色
        # 否则按照官方原版labelme的方式，通过label哈希设置
        hash_colors = mainwin._get_rgb_by_label(hashtext)
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
                showtext, r, g, b
            )
        )

        # 注意，只有用shape_color才能全局调整颜色，下面六个属性是单独调的
        # 线的颜色
        rgb_ = parse_htext(mainwin.xllabel.get_hashtext(labelattr, 'label_line_color'))
        shape.line_color = QtGui.QColor(*seleter('line_color', rgb_))
        # 顶点颜色
        rgb_ = parse_htext(mainwin.xllabel.get_hashtext(labelattr, 'label_vertex_fill_color'))
        shape.vertex_fill_color = QtGui.QColor(*seleter('vertex_fill_color', rgb_))
        # 悬停时顶点颜色
        shape.hvertex_fill_color = QtGui.QColor(*seleter('hvertex_fill_color', (255, 255, 255)))
        # 填充颜色
        shape.fill_color = QtGui.QColor(*seleter('fill_color', (r, g, b, 128)))
        # 选中时的线、填充颜色
        shape.select_line_color = QtGui.QColor(*seleter('select_line_color', (255, 255, 255)))
        shape.select_fill_color = QtGui.QColor(*seleter('select_fill_color', (r, g, b, 155)))

        return label_list_item

    def new_shape(self):
        """ 新建标注框时的规则
        """
        mainwin = self.mainwin
        items = mainwin.uniqLabelList.selectedItems()
        text = None
        if items:
            text = items[0].data(Qt.UserRole)
        flags = {}
        group_id = None
        if mainwin._config["display_label_popup"] or not text:
            previous_text = mainwin.labelDialog.edit.text()

            shape = Shape()
            shape.label = self.get_default_label(shape=mainwin.canvas.shapes[-1])
            shape = mainwin.labelDialog.popUp2(shape, mainwin)
            if shape is not None:
                text, flags, group_id = shape.label, shape.flags, shape.group_id

            if not text:
                mainwin.labelDialog.edit.setText(previous_text)

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

    def get_default_label(self, shape=None):
        xllabel = self.mainwin.xllabel
        label = xllabel.cfg.get('default_label', '')
        if xllabel.auto_rec_text and xllabel.xlapi and shape:
            k = 'label' if 'label' in xllabel.keys else 'text'
            text, score = xllabel.rec_text(shape.points)
            label = xllabel.set_label_attr(label, k, text)
            label = xllabel.set_label_attr(label, 'score', score)
        return label


class 文字通用(xllabelme):
    def get_default_label(self, shape=None):
        d = {'text': '', 'category': '', 'text_kv': 'value', 'text_type': '印刷体'}
        return json.dumps(d, ensure_ascii=False)


class m2302中科院题库(xllabelme):
    def get_default_label(self, shape=None):
        from pyxllib.cv.xlcvlib import xlcv
        from pyxlpr.data.imtextline import TextlineShape

        # 1 获得基本内容。如果开了识别接口，要调api。
        xllabel = self.mainwin.xllabel
        points = [(p.x(), p.y()) for p in shape.points]
        d = None
        if xllabel.auto_rec_text and xllabel.xlapi and shape:
            # 识别指定的points区域

            im = xlcv.get_sub(xllabel.mainwin.arr_image, points, warp_quad=True)
            try:
                d = xllabel.xlapi.priu_api('content_ocr', im, filename=xllabel.mainwin.filename)
            except requests.exceptions.ConnectionError:
                pass
        if d is None:  # 设默认值
            d = {'line_id': 1, 'content_type': '印刷体', 'content_class': '文本', 'text': ''}

        # 2 获得line_id
        line_id = 1
        shapes = xllabel.mainwin.canvas.shapes  # 最后一个框
        if len(shapes) > 1:
            sp = shapes[-2]  # 当前框会变成shapes[-1]，所以要取shapes[-2]才是上一次建立的框
            line_id0 = json.loads(sp.label).get('line_id', 1)
            if TextlineShape(points).in_the_same_line(TextlineShape([(p.x(), p.y()) for p in sp.points])):
                line_id = line_id0
            else:
                line_id = line_id0 + 1
        d['line_id'] = line_id

        return json.dumps(d, ensure_ascii=False)


class m2303表格标注(原版labelme):
    def get_default_label(self, shape=None):
        """ 这个识别可以做的更精细的，不过这个项目不一定接，现在只做一个最基础性的功能 """
        # 表格, 可见横线, 可见竖线, 不可见横线, 不可见竖线

        poly = ShapelyPolygon.gen([(p.x(), p.y()) for p in shape.points])
        bounds = poly.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]

        if height > width:
            return '可见竖线'
        else:
            return '可见横线'


def __2_xllabel中介组件():
    pass


class XlLabel:
    """
    开发指南：尽量把对xllabelme的扩展，都写到这个类里，好集中统一管理
    """

    def __init__(self, parent):
        self.mainwin = parent

        self.read_config()
        self.default_shape_color_mode = 0  # 用来设置不同的高亮检查格式，会从0不断自增。然后对已有配色方案轮循获取。

        self.cur_img = {}  # 存储当前图片的ndarray数据。只有一条数据，k=图片路径，v=图片数据
        self.image_root = None  # 图片所在目录。有特殊功能用途，用在json和图片没有放在同一个目录的情况。
        # 这里可以配置显示哪些可用项目标注，有时候可能会需要定制化
        self.reset()
        # self.config_label_menu()  # 配置界面
        self.xlapi = None

    def reset(self, mode=None):
        """ 更新配置 """
        # 0 旧项目相关配置要回退
        project = getattr(self.mainwin, 'project', None)
        if project:
            project.destroy()

        # 1 确定mode
        if mode:
            self.meta_cfg['current_mode'] = mode
        if self.meta_cfg['current_mode'] not in _CONFIGS:
            self.meta_cfg['current_mode'] = '文字通用'
        mode = self.meta_cfg['current_mode']

        # 2 预设mode或自定义mode的详细配置
        default_cfg = {
            'attrs': [],
            'editable': False,
            'label_shape_color': [],
            'label_line_color': [],
            'label_vertex_fill_color': [],
        }

        if mode in _CONFIGS:
            cfg = _CONFIGS[mode]
        else:
            cfg = self.meta_cfg['custom_modes'][mode]

        # 3 _attrs的处理
        def _attrs2attrs(_attrs):
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

        if '_attrs' in cfg:
            cfg['attrs'] = _attrs2attrs(cfg['_attrs'])
            del cfg['_attrs']

        # 4 设置该模式的详细配置
        default_cfg.update(cfg)
        cfg = default_cfg
        self.keyidx = {x['key']: i for i, x in enumerate(cfg['attrs'])}
        for x in cfg['attrs']:
            if isinstance(x['items'], (list, tuple)):
                if x.get('editable', 0):
                    x['items'] = list(x['items'])
                else:
                    x['items'] = tuple(x['items'])
        self.keys = [x['key'] for x in cfg['attrs']]
        self.hide_attrs = [x['key'] for x in cfg['attrs'] if x['show'] == 0]
        self.cfg = cfg

        # 5 确定当前配色方案
        ms = re.findall(r'(label_shape_color(?:\d+)?),', ','.join(self.cfg.keys()))
        if ms:
            idx = self.default_shape_color_mode % len(ms)
            self.cfg['label_shape_color'] = self.cfg[ms[idx]]

        # 6 设置项目
        if project:
            self.mainwin.project = self.open_project()

    def config_label_menu(self):
        """ Label菜单栏
        """

        def get_task_menu():
            # 1 关联选择任务后的回调函数
            def func(action):
                # 1 内置数据格式
                action.setCheckable(True)
                action.setChecked(True)
                self.reset(action.text())
                # 一个时间，只能开启一个模式
                for a in task_menu.findChildren(QAction):
                    if a is not action:
                        a.setChecked(False)

                # 2 如果是自定义模式，弹出编辑窗
                pass

                # 3 保存配置
                self.save_config()

            task_menu = QMenu('任务', label_menu)
            task_menu.triggered.connect(func)

            # 2 往Label菜单添加选项功能
            actions = []
            for x in _CONFIGS.keys():
                actions.append(QAction(x, task_menu))
            if self.meta_cfg['custom_modes']:
                actions.append(None)
                for x in self.meta_cfg['custom_modes'].keys():
                    actions.append(QAction(x, task_menu))
            # 激活初始mode模式的标记
            for a in actions:
                if a.text() == self.meta_cfg['current_mode']:
                    a.setCheckable(True)
                    a.setChecked(True)
            utils.addActions(task_menu, actions)
            return task_menu

        def get_auto_rec_text_action():
            def func(x):
                self.auto_rec_text = x

                if self.auto_rec_text:
                    os.environ['XlAiAccounts'] = 'eyJwcml1IjogeyJ0b2tlbiI6ICJ4bGxhYmVsbWV5XipBOXlraiJ9fQ=='
                    try:
                        self.xlapi = XlAiClient()
                    except ConnectionError:
                        # 没有网络
                        self.xlapi = None
                        a.setChecked(False)
                        # 提示
                        msg_box = QMessageBox(QMessageBox.Information, "xllabelme标注工具：连接自动识别的API失败",
                                              "尝试连接xmutpriu.com的api失败，请检查网络问题，比如关闭梯子。\n"
                                              '如果仍然连接不上，可能是服务器的问题，请联系"管理员"。')
                        msg_box.setStandardButtons(QMessageBox.Ok)
                        msg_box.exec_()

                self.save_config()

            a = QAction('自动识别文本内容', label_menu)
            a.setCheckable(True)
            if self.auto_rec_text:
                a.setChecked(True)
                func(True)
            else:
                a.setChecked(False)
            a.triggered.connect(func)
            return a

        def get_set_image_root_action():
            a = QAction('设置图片所在目录', label_menu)

            def func():
                self.image_root = XlPath(QFileDialog.getExistingDirectory(self.image_root))
                self.mainwin.importDirImages(self.mainwin.lastOpenDir)

            a.triggered.connect(func)
            return a

        label_menu = self.mainwin.menus.label
        label_menu.addMenu(get_task_menu())
        label_menu.addSeparator()
        label_menu.addAction(get_auto_rec_text_action())
        label_menu.addAction(get_set_image_root_action())

    def parse_shape(self, shape):
        """ xllabelme相关扩展功能，常用的shape解析

        :return:
            showtext，需要重定制展示内容
            hashtext，用于哈希颜色计算的label
            labeldata，解析成字典的数据，如果其本身标注并不是字典，则该参数为空值
        """
        # 1 默认值，后面根据参数情况会自动调整
        showtext = shape.label
        labelattr = self.get_labelattr(shape.label)

        # 2 hashtext
        # self.hashtext成员函数只简单分析labelattr，作为shape_color需要扩展考虑更多特殊情况
        hashtext = self.get_hashtext(labelattr)
        if not hashtext:
            if 'label' in labelattr:
                hashtext = labelattr['label']
            elif 'id' in labelattr:
                hashtext = labelattr['id']
            elif labelattr:
                hashtext = next(iter(labelattr.values()))
            else:
                hashtext = showtext
        hashtext = str(hashtext)

        # 3 showtext
        if labelattr:
            # 3.1 隐藏部分属性
            hide_attrs = self.hide_attrs
            showdict = {k: v for k, v in labelattr.items() if k not in hide_attrs}
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
            return self.cfg['attrs'][idx]
        else:
            return default

    def read_config(self):
        self.configpath = XlPath.userdir() / ".xllabelme"
        if self.configpath.is_file():
            self.meta_cfg = self.configpath.read_json()
        else:
            self.meta_cfg = {'current_mode': '文字通用',
                             'custom_modes': {},
                             'auto_rec_text': False,
                             }
        self.auto_rec_text = self.meta_cfg.get('auto_rec_text', False)  # 新建框的时候，是否自动识别文本内容
        # auto_rec_text和xlapi两个参数不是冗余，是分别有不同含义的，最好不要去尝试精简掉！
        # auto_rec_text是设置上是否需要每次自动识别，xlapi是网络、api是否确实可用

        if self.meta_cfg['current_mode'] == 'm2302阅深题库':
            self.meta_cfg['current_mode'] = 'm2302中科院题库'

    def save_config(self):
        if self.mainwin.lastOpenDir:
            self.meta_cfg['lastOpenDir'] = XlPath(self.mainwin.lastOpenDir).as_posix()
        self.meta_cfg['auto_rec_text'] = self.auto_rec_text
        self.configpath.write_json(self.meta_cfg, encoding='utf8', indent=2, ensure_ascii=False)

    def __labelattr(self):
        """ label相关的操作

        labelme原始的格式，每个shape里的label字段存储的是一个str类型
        我为了扩展灵活性，在保留其str类型的前提下，存储的是一串可以解析为json字典的数据
        前者称为labelstr类型，后者称为labelattr格式

        下面封装了一些对label、labelattr进行操作的功能
        """

    @classmethod
    def json_dumps(cls, label):
        return json.dumps(label, ensure_ascii=False)

    def get_hashtext(self, labelattr, mode='label_shape_color'):
        """
        :param labelattr:
        :param mode:
            label_shape_color
            label_line_color
            label_vertex_fill_colorS
        :return:
            如果 labelattr 有对应key，action也有开，则返回拼凑的哈希字符串值
            否则返回 None
        """
        ls = []
        attrs = self.cfg.get(mode, [])
        for k in attrs:
            if k in labelattr:
                ls.append(str(labelattr[k]))
        if ls:
            return ', '.join(ls)

    @classmethod
    def update_other_data(cls, shape):
        labelattr = cls.get_labelattr(shape.label, shape.other_data)
        if labelattr:
            shape.label = cls.json_dumps(labelattr)
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
        return cls.json_dumps(labelattr)

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
                if self.auto_rec_text and self.xlapi:
                    labelattr = self.get_labelattr(x.label)
                    labelattr['text'], labelattr['score'] = self.rec_text(x.points)
                    x.label = self.json_dumps(labelattr)
            else:
                x.label = self.set_label_attr(x.label, 'text', text)

        return x

    def __smart_label(self):
        """ 智能标注相关 """

    def rec_text(self, points):
        """ 文字识别或者一些特殊的api接口 """
        from pyxllib.cv.xlcvlib import xlcv
        # 识别指定的points区域
        if isinstance(points[0], QPointF):
            points = [(p.x(), p.y()) for p in points]
        im = xlcv.get_sub(self.mainwin.arr_image, points, warp_quad=True)

        texts, scores = [], []  # 因图片太小等各种原因，没有识别到结果，默认就设空值
        try:
            d = self.xlapi.priu_api('basicGeneral', im)
            if 'shapes' in d:
                texts = [sp['label']['text'] for sp in d['shapes']]
                scores = [sp['label']['score'] for sp in d['shapes']]
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

    def content_ocr(self, shape):
        """ 主要给"m2302中科院题库"用的 """
        from pyxllib.cv.xlcvlib import xlcv
        from pyxlpr.data.imtextline import TextlineShape

        # 1 获得基本内容。如果开了识别接口，要调api。
        points = shape.points
        d = None
        if self.auto_rec_text and self.xlapi and shape:
            # 识别指定的points区域
            if isinstance(points[0], QPointF):
                points = [(p.x(), p.y()) for p in points]
            im = xlcv.get_sub(self.mainwin.arr_image, points, warp_quad=True)
            try:
                d = self.xlapi.priu_api('content_ocr', im, filename=self.mainwin.filename)
            except requests.exceptions.ConnectionError:
                pass
        if d is None:
            d = json.loads(_CONFIGS['m2302中科院题库']['default_label'])

        # 2 获得line_id
        line_id = 1
        shapes = self.mainwin.canvas.shapes  # 最后一个框
        if len(shapes) > 2:
            sp = shapes[-2]  # 当前框会变成shapes[-1]，所以要取shapes[-2]才是上一次建立的框
            line_id0 = json.loads(sp.label)['line_id']
            if TextlineShape(points).in_the_same_line(TextlineShape([(p.x(), p.y()) for p in sp.points])):
                line_id = line_id0
            else:
                line_id = line_id0 + 1
        d['line_id'] = line_id

        return json.dumps(d, ensure_ascii=False)

    def __right_click_shape(self):
        """ 扩展shape右键操作菜单功能
        """

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

    def convert_to_rectangle_action(self):
        """ 将shape形状改为四边形 """

        def func():
            item, shape = self.get_current_select_shape()
            if shape:
                shape.shape_type = 'rectangle'
                pts = [(p.x(), p.y()) for p in shape.points]
                l, t, r, b = rect_bounds(pts)
                shape.points = [QPointF(l, t), QPointF(r, b)]
                mainwin.updateShape(shape, item)
                mainwin.setDirty()

        mainwin = self.mainwin
        a = utils.newAction(mainwin,
                            mainwin.tr("Convert to Rectangle"),
                            func,
                            None,  # shortcut
                            None,  # icon
                            mainwin.tr("将当前shape转为Rectangle矩形")  # 左下角的提示
                            )
        return a

    def split_shape_action(self):
        """ 将一个框拆成两个框

        TODO 支持对任意四边形的拆分
        策略1：现有交互机制上，选择参考点后，拆分出多边形
        策略2：出来一把剪刀，通过画线指定切分的详细形式
        """

        def func():
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
                if self.auto_rec_text and self.xlapi:
                    self.update_shape_text(shape)
                    self.update_shape_text(shape2)
                else:  # 否则按几何比例重分配文本
                    from pyxlpr.data.imtextline import merge_labels_by_widths
                    text = self.get_labelattr(shape.label).get('text', '')
                    text1, text2 = merge_labels_by_widths(list(text), [p - l, r - p], '')
                    self.update_shape_text(shape, text1)
                    self.update_shape_text(shape2, text2)

                # 3 更新到shapes里
                mainwin.canvas.selectedShapes.append(shape2)
                mainwin.addLabel(shape2)
                shapes = mainwin.canvas.shapes
                idx = shapes.index(shape)
                shapes = shapes[:idx + 1] + [shape2] + shapes[idx + 1:]  # 在相邻位置插入新的shape
                mainwin.updateShapes(shapes)
                mainwin.setDirty()

        mainwin = self.mainwin
        a = utils.newAction(mainwin,
                            mainwin.tr("Split Shape"),
                            func,
                            None,  # shortcut
                            None,  # icon
                            mainwin.tr("在当前鼠标点击位置，将一个shape拆成两个shape（注意，该功能会强制拆出两个矩形框）")
                            )
        return a

    def change_check(self, update=True):
        """ 设置不同的高亮格式 """
        if update:
            self.default_shape_color_mode += 1
            self.reset()
            self.mainwin.updateLabelListItems()

        # 提示给出更具体的使用的范式配置
        act = self.mainwin.changeCheckAction
        tip = act.toolTip()
        tip = re.sub(r'当前配置.*$', '', tip)
        tip += '当前配置：' + ', '.join(self.cfg['label_shape_color'])
        act.setStatusTip(tip)
        act.setToolTip(tip)

    def open_project(self):
        try:
            project = eval(self.mainwin.xllabel.meta_cfg['current_mode'])(self.mainwin)
        except NameError:
            project = 原版labelme(self.mainwin)
        return project
