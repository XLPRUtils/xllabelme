# TODO 可以把软件改成运行中加载配置文件的方式
#   例如如果有 "config.ini" 文件则读取
#   否则使用该文件的默认配置

TYPE_ITEMS = ['印刷体', '手写体', '印章', '身份证', '表格', '其它证件类', '其它']
KV_ITEMS = ['key', 'value']

SROIE_KV_ITEMS = ['other', 'key', 'value']

SROIE_CLASS_ITEMS = [
    'other',
    'company',
    'address',
    'date',
    'total'
]

# 一种精简的配置方法，需要使用_py2ls转成规范的配置结构
COCO = [
    ['id', 1, 'int'],
    ['label', 1, 'str'],
    ['category_id', 1, 'int'],
    ['content_type', 1, 'str', tuple(TYPE_ITEMS)],
    # ['content_class', 1, 'str', tuple(CLASS_ITEMS)],
    ['content_kv', 1, 'str', tuple(KV_ITEMS)],
    ['sroie_class', 1, 'str', tuple(SROIE_CLASS_ITEMS)],
    ['sroie_kv', 1, 'str', tuple(SROIE_KV_ITEMS)],
    ['bbox', 0],
    ['area', 0],
    ['image_id', 0],
    ['segmentation', 0],
    ['iscrowd', 0],
]


def _py2ls(ls):
    """
    :param ls: 原始手动录入的数据格式
    :return: dict[attr, Item]
    """
    res = []
    for x in ls:
        # 1 补长对齐
        if len(x) < 4:
            x += [None] * (4 - len(x))
        # 2 设置属性值
        d = {'key': x[0], 'show': x[1], 'type': x[2], 'items': x[3]}
        if isinstance(x[3], list):
            d['editable'] = 1
        res.append(d)

    return res


COCO = _py2ls(COCO)
