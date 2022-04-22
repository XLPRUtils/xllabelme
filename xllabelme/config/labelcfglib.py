import json
import os.path as osp

from PyQt5.QtWidgets import QInputDialog

from pyxllib.xl import XlPath
from pyxllib.algo.pupil import make_index_function
from pyxllib.prog.pupil import DictTool

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
              ]
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


class LabelCfg:
    def __init__(self, parent):
        self.parent = parent
        self.configpath = XlPath.userdir() / ".xllabelme_labelcfg"
        if self.configpath.is_file():
            self.meta_cfg = self.configpath.read_json()
        else:
            self.meta_cfg = {'current_mode': 'xllabelme',
                             'custom_modes': {}
                             }
        # 这里可以配置显示哪些可用项目标注，有时候可能会需要定制化
        self.reset()
        self.config_menu_label()  # 配置界面

    def reset(self, mode=None):
        # 1 确定mode
        if mode:
            self.meta_cfg['current_mode'] = mode
        mode = self.meta_cfg['current_mode']

        # 2 预设mode或自定义mode的详细配置
        cfg = {
            'attrs': [],
            'autodict': True,
            'editable': False,
            'label_shape_color': [],
            'label_line_color': [],
            'label_vertex_fill_color': [],
        }

        if mode in _CONFIGS:
            cfg2 = _CONFIGS[mode]
        else:
            cfg2 = self.meta_cfg['custom_modes'][mode]

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

        if '_attrs' in cfg2:
            cfg2['attrs'] = _attrs2attrs(cfg2['_attrs'])
            del cfg2['_attrs']

        # 4 设置该模式的详细配置
        cfg.update(cfg2)
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

    def get_default_label(self, *, shape=None, mainwin=None):
        """ 新建shape的时候，使用的默认label值

        :param shape: 可以输入一个shape供参考

        这里有办法获取原图，也有办法获取标注的shape，从而可以智能推断，给出识别值的
        """
        from pyxllib.xlcv import xlcv
        if mainwin:
            mainwin.cvimg = xlcv.read(mainwin.imagePath)

        label = json.dumps({'text': '', 'type': '印刷体'}, ensure_ascii=False)
        return label

    def config_menu_label(self):
        """ Label菜单栏
        """
        from PyQt5.QtWidgets import QAction

        # 1 关联label操作的回调函数
        def func(action):
            # 1 内置数据格式
            action.setCheckable(True)
            action.setChecked(True)
            self.reset(action.text())
            # 一个时间，只能开启一个模式
            for a in parent.findChildren(QAction):
                if a is not action:
                    a.setChecked(False)

            # 2 如果是自定义模式，弹出编辑窗
            pass

            # 3 保存配置
            self.save_config()

        parent = self.parent.menus.label
        parent.triggered.connect(func)

        # 2 往Label菜单添加选项功能
        actions = []
        for x in _CONFIGS.keys():
            actions.append(QAction(x, parent))
        if self.meta_cfg['custom_modes']:
            actions.append(None)
            for x in self.meta_cfg['custom_modes'].keys():
                actions.append(QAction(x, parent))
        # 激活初始mode模式的标记
        for a in actions:
            if a.text() == self.meta_cfg['current_mode']:
                a.setCheckable(True)
                a.setChecked(True)
        utils.addActions(parent, actions)

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
