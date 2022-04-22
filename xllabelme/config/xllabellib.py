import json
import os.path as osp
import time

from PyQt5.QtCore import QPointF
from PyQt5.QtWidgets import QMenu, QAction

from pyxllib.file.specialist import XlPath
from pyxllib.algo.geo import rect_bounds
from pyxllib.algo.pupil import make_index_function
from pyxllib.prog.pupil import DictTool
from pyxllib.gui.qt import WaitMessageBox

from xllabelme import utils

_CONFIGS = {
    'labelme': {'autodict': False},
    'xllabelme': {},
    '文字通用':
        {'_attrs':
             [['text', 1, 'str'],
              ['class', 1, 'str'],
              ['kv', 1, 'str', ('other', 'key', 'value')],
              ['type', 1, 'str', ('印刷体', '手写体', '其它')],
              ],
         'label_line_color': ['class'],
         'label_vertex_fill_color': ['kv']
         },
    '核酸检测':
        {'_attrs':
             [['text', 1, 'str'],
              ["content_class", 1, "str", ("其它类", "姓名", "身份证号", "联系方式", "采样时间", "检测时间", "核酸结果")],
              ['content_kv', 1, 'str', ('key', 'value')],
              ],
         'label_shape_color': 'content_class'.split(','),
         'default_label': json.dumps({'text': '', 'content_class': '其它类', 'content_kv': 'value'}, ensure_ascii=False),
         },
    'XlCoco': {
        '_attrs':
            [['id', 1, 'int'],
             ['label', 1, 'str'],
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
        'label_vertex_fill_color': 'dt_category_id,dt_category_name'.split(','),
    },
    'Sroie2019+':
        {'_attrs':
             [['label', 1, 'str'],
              ['sroie_class', 1, 'str', ('other', 'company', 'address', 'date', 'total')],
              ['sroie_kv', 1, 'str', ('other', 'key', 'value')],
              ]
         },
}


class XlLabel:
    def __init__(self, parent):
        self.mainwin = parent
        self.configpath = XlPath.userdir() / ".xllabelme_labelcfg"
        if self.configpath.is_file():
            self.meta_cfg = self.configpath.read_json()
        else:
            self.meta_cfg = {'current_mode': 'xllabelme',
                             'custom_modes': {}
                             }

        # 新建框的时候，是否自动识别文本内容
        self.auto_rec_text = False
        self.cur_img = {}  # 存储当前图片的ndarray数据。只有一条数据，k=图片路径，v=图片数据

        # 这里可以配置显示哪些可用项目标注，有时候可能会需要定制化
        self.reset()
        # self.config_label_menu()  # 配置界面

    def reset(self, mode=None):
        # 1 确定mode
        if mode:
            self.meta_cfg['current_mode'] = mode
        mode = self.meta_cfg['current_mode']

        # 2 预设mode或自定义mode的详细配置
        default_cfg = {
            'attrs': [],
            'autodict': True,
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

        if self.auto_rec_text and shape:
            k = 'label' if 'label' in self.keys else 'text'
            text, score = self.rec_text(self.mainwin.imagePath, shape)
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
                if x:
                    self.ensure_ppocr()

            a.triggered.connect(func)
            return a

        label_menu = self.mainwin.menus.label
        label_menu.addMenu(get_task_menu())
        label_menu.addSeparator()
        label_menu.addAction(get_auto_rec_text_action())

    def parse_shape(self, shape):
        """ xllabelme相关扩展功能，常用的shape解析

        :return:
            showtext，需要重定制展示内容
            hashtext，用于哈希颜色计算的label
            labeldata，解析成字典的数据，如果其本身标注并不是字典，则该参数为空值
        """
        # 1 默认值，后面根据参数情况会自动调整
        showtext = shape.label
        labelattr = self.get_label_attr(shape.label)

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

    def save_config(self):
        self.configpath.write_json(self.meta_cfg, encoding='utf8', indent=2, ensure_ascii=False)

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
        labelattr = cls.get_label_attr(shape.label, shape.other_data)
        if labelattr:
            shape.label = json.dumps(labelattr, ensure_ascii=False)
            shape.other_data = {}

    @classmethod
    def get_label_attr(cls, label, other_data=None):
        labelattr = DictTool.json_loads(label)

        if other_data:
            # 如果有other_data，非字典结构的label也会强制升为字典
            if not labelattr:
                labelattr['label'] = label
            # 如果有扩展字段，则也将数据强制取入 labelattr
            labelattr.update(other_data)
        return labelattr

    @classmethod
    def set_label_attr(cls, label, k, v):
        """ 修改labelattr字典值 """
        labelattr = cls.get_label_attr(label)
        if not labelattr:  # 如果有other_data，非字典结构的label也会强制升为字典
            labelattr['label'] = label
        labelattr[k] = v
        return json.dumps(labelattr, ensure_ascii=False)

    def __smart_label(self):
        """ 智能标注相关 """

    def ensure_ppocr(self):
        if not hasattr(self, 'ppocr'):
            with WaitMessageBox(self.mainwin, 'PaddleOCR模型初始化中，请稍等一会...'):
                from pyxlpr.paddleocr import PaddleOCR
                self.ppocr = PaddleOCR.build_ppocr()

    def rec_text(self, image_path, shape):
        from pyxllib.xlcv import xlcv
        if image_path not in self.cur_img:
            self.cur_img = {image_path: xlcv.read(image_path)}
        img = self.cur_img[image_path]
        pts = [(p.x(), p.y()) for p in shape.points]
        im = xlcv.get_sub(img, pts, warp_quad=True)
        text, score = self.ppocr.rec_singleline(im)
        return text, score

    def __right_click_shape(self):
        """ 扩展shape右键操作菜单功能
        """
        pass

    def get_current_select_shape(self):
        """ 如果当前没有选中item（shape），会返回None """
        mainwin = self.mainwin
        if not mainwin.canvas.editing():
            return
        item = mainwin.currentItem()
        if item is None:
            return
        shape = item.shape()
        return shape

    def convert_to_rectangle_action(self):
        """ 将shape形状改为四边形 """

        def func():
            shape = self.get_current_select_shape()
            if shape:
                shape.shape_type = 'rectangle'
                pts = [(p.x(), p.y()) for p in shape.points]
                l, t, r, b = rect_bounds(pts)
                shape.points = [QPointF(l, t), QPointF(r, b)]

        mainwin = self.mainwin
        a = utils.newAction(mainwin,
                            mainwin.tr("Convert to Rectangle"),
                            func,
                            None,  # shortcut
                            None,  # icon
                            mainwin.tr("将当前shape转为Rectangle矩形")  # 左下角的提示
                            )
        return a
