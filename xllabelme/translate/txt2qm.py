import xml.etree.ElementTree as ET
from xml.dom import minidom
import subprocess

from pyxllib.file.specialist import XlPath


def ts2txt():
    # 读取 .ts 文件
    tree = ET.parse('zh_CN.ts')
    root = tree.getroot()

    # 提取 source 和 translation 元素
    sources = root.findall(".//context/message/source")
    translations = root.findall(".//context/message/translation")

    # 打包成元组列表并按 source 升序排序
    messages = sorted(zip(sources, translations), key=lambda x: x[0].text)

    # 将 source 和 translation 写入文本文件
    with open('zh_CN.txt', 'w', encoding='utf8') as f:
        for source, translation in messages:
            source_text = source.text.strip() if source.text else ''
            translation_text = translation.text.strip() if translation.text else ''
            source_text = source_text.replace('\n', r'\n')
            translation_text = translation_text.replace('\n', r'\n')
            f.write(f"{source_text}\n{translation_text}\n\n")


def txt2ts():
    # 读取文本文件
    with open('zh_CN.txt', 'r', encoding='utf8') as f:
        lines = f.readlines()

    # 将文本内容转换为 source 和 translation 元素
    messages = []
    for i in range(0, len(lines), 3):
        if i + 1 >= len(lines):
            continue
        source_text = lines[i].strip().replace(r'\n', '\n')
        translation_text = lines[i + 1].strip().replace(r'\n', '\n')
        source = ET.Element('source')
        source.text = source_text
        translation = ET.Element('translation')
        translation.text = translation_text
        message = ET.Element('message')
        message.append(source)
        message.append(translation)
        messages.append(message)

    # 创建根元素和 context 元素
    root = ET.Element('TS')
    context = ET.Element('context')
    name = ET.Element('name')
    name.text = 'XlMainWindow'
    context.append(name)
    for message in messages:
        context.append(message)
    root.append(context)

    # 将 ElementTree 转换为 minidom 对象
    tree = ET.ElementTree(root)
    xml_str = ET.tostring(tree.getroot(), encoding='utf-8')
    minidom_tree = minidom.parseString(xml_str)

    # 美化输出并写入 .ts 文件
    pretty_xml_str = minidom_tree.toprettyxml(indent='  ', encoding='utf-8')
    with open('zh_CN.ts', 'wb') as f:
        f.write(pretty_xml_str)


def ts2qm():
    subprocess.run(['lrelease', 'zh_CN.ts', '-qm', 'zh_CN.qm'])


def qm2py():
    """ 后记：pyinstaller可以打包文件数据，不用自己转到代码变量里，这个函数其实没用了

    但实测中又发现有bug，还是得先用我这个方式~
    """
    # 读取 .qm 文件的二进制数据
    with open("zh_CN.qm", "rb") as file:
        qm_data = file.read()

    # 将二进制数据转换为 Python 可以处理的格式
    qm_data_as_string = ", ".join(f"0x{byte:02x}" for byte in qm_data)

    # 创建一个包含二进制数据的 Python 文件
    with open("../ts.py", "w") as file:
        file.write("zh_CN = b'")
        file.write("".join(f"\\x{byte:02x}" for byte in qm_data))
        file.write("'\n")
        file.write("en = b''\n")  # 英文什么都不写，


def refine_txt():
    """ 优化txt文件内容，查重以及重排序 """

    def sort_groups(groups):
        sorted_groups = sorted(groups, key=lambda x: x[0].strip().lower())
        return sorted_groups

    def check_duplicates(groups):
        duplicates = set()
        seen = set()
        for group in groups:
            first_line = group[0].strip().lower()
            if first_line and first_line in seen:
                duplicates.add(first_line)
            seen.add(first_line)
        return duplicates

    def group_lines(lines, group_size=3):
        if len(lines) % 3:
            lines += [''] * (3 - (len(lines) % 3))
        groups = [lines[i:i + group_size] for i in range(0, len(lines), group_size)]
        return groups

    def ungroup_lines(groups):
        lines = []
        for group in groups:
            lines.extend(group)
        return lines

    lines = XlPath('zh_CN.txt').read_text().splitlines()
    groups = group_lines(lines)
    sorted_groups = sort_groups(groups)
    duplicates = check_duplicates(groups)

    if duplicates:
        print("以下是重复的内容：")
        for duplicate in duplicates:
            print(duplicate)

    XlPath('zh_CN.txt').write_text('\n'.join(ungroup_lines(sorted_groups)))


def main():
    refine_txt()
    txt2ts()
    ts2qm()
    qm2py()


if __name__ == '__main__':
    # 1 这个最开始执行一次即可，以后不用执行
    # ts2txt()
    # 以 zh_CN.txt 为原始标注文件

    # 2 自动生成其他所有衍生文件
    main()
