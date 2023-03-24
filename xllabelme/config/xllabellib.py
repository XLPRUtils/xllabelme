import json
import os
import os.path as osp
import time
from statistics import mean

import requests

from PyQt5.QtCore import QPointF
from PyQt5.QtWidgets import QMenu, QAction, QFileDialog

from pyxllib.file.specialist import XlPath
from pyxllib.algo.geo import rect_bounds
from pyxllib.algo.pupil import make_index_function
from pyxllib.prog.pupil import DictTool
from pyxlpr.ai.clientlib import XlAiClient

from xllabelme import utils

_CONFIGS = {
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
    'm2302阅深题库':  # 这是比较旧的一套配置字段名
        {'_attrs':
             [['content_type', 1, 'str', ('印刷体', '手写体')],
              ["content_class", 1, "str", ("文本", "公式", "图片", "表格")],
              ['text', 1, 'str'],
              ],
         'label_shape_color': 'content_type,content_class'.split(','),
         # 'label_vertex_fill_color': 'content_kv'.split(','),
         'default_label': json.dumps({'content_type': '印刷体',
                                      'content_class': '文本', 'text': ''}, ensure_ascii=False),
         },
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


class XlLabel:
    """
    开发指南：尽量把对xllabelme的扩展，都写到这个类里，好集中统一管理
    """

    def __init__(self, parent):
        self.mainwin = parent

        self.read_config()

        self.cur_img = {}  # 存储当前图片的ndarray数据。只有一条数据，k=图片路径，v=图片数据
        self.image_root = None  # 图片所在目录。有特殊功能用途，用在json和图片没有放在同一个目录的情况。
        # 这里可以配置显示哪些可用项目标注，有时候可能会需要定制化
        self.reset()
        # self.config_label_menu()  # 配置界面
        self.xlapi = None

    def reset(self, mode=None):
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

    def get_default_label(self, *, shape=None):
        """ 新建shape的时候，使用的默认label值

        :param shape: 可以输入一个shape供参考

        这里有办法获取原图，也有办法获取标注的shape，从而可以智能推断，给出识别值的
        """
        label = self.cfg.get('default_label', '')
        if self.auto_rec_text and self.xlapi and shape:
            if self.meta_cfg['current_mode'] == 'm2302阅深题库':
                label = self.content_ocr(shape.points)
            else:
                k = 'label' if 'label' in self.keys else 'text'
                text, score = self.rec_text(shape.points)
                label = self.set_label_attr(label, k, text)
                label = self.set_label_attr(label, 'score', score)
        return label

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
            a = QAction('自动识别文本内容', label_menu)
            a.setCheckable(True)
            a.setChecked(self.auto_rec_text)

            def func(x):
                self.auto_rec_text = x

                if self.auto_rec_text:
                    os.environ['XlAiAccounts'] = 'eyJwcml1IjogeyJ0b2tlbiI6ICJ4bGxhYmVsbWV5XipBOXlraiJ9fQ=='
                    try:
                        self.xlapi = XlAiClient()
                    except ConnectionError:
                        # 没有网络
                        self.xlapi = None

                self.save_config()

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

    def save_config(self):
        if self.mainwin.lastOpenDir:
            self.meta_cfg['lastOpenDir'] = XlPath(self.mainwin.lastOpenDir).as_posix()
        self.meta_cfg['auto_rec_text'] = self.auto_rec_text
        self.configpath.write_json(self.meta_cfg, encoding='utf8', indent=2, ensure_ascii=False)

    def __labelattr(self):
        """ label相关的操作

        labelme原始的格式，每个shape里的label字段存储的是一个str类型
        我为了扩展灵活性，在保留起str类型的前提下，存储的是一串可以解析为json字典的数据
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
            label_vertex_fill_color
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

    def content_ocr(self, points):
        """ 主要给"m2302阅深题库"用的 """
        from pyxllib.cv.xlcvlib import xlcv
        # 识别指定的points区域
        if isinstance(points[0], QPointF):
            points = [(p.x(), p.y()) for p in points]
        im = xlcv.get_sub(self.mainwin.arr_image, points, warp_quad=True)

        try:
            d = self.xlapi.priu_api('content_ocr', im, filename=self.mainwin.filename)
            label = json.dumps(d)
        except requests.exceptions.ConnectionError:
            label = _CONFIGS['m2302阅深题库']['default_label']

        return label

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
