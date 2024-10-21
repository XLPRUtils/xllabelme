title 生成xllabelme.exe
call conda activate xllabelme

pyinstaller xllabelme.spec
move dist\xllabelme.exe D:\home\chenkunze\data\m2303表格标注\3、工具汇总
ren D:\home\chenkunze\data\m2303表格标注\3、工具汇总\xllabelme.exe "xllabelme v5.1.7w.exe"
start d:\home\chenkunze\data\m2303表格标注\3、工具汇总
