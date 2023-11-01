title 生成xllabelme.exe
call conda activate xllabelme

pyinstaller xllabelme.spec
move dist\xllabelme.exe C:\home\chenkunze\data\m2303表格标注\3、工具汇总
ren C:\home\chenkunze\data\m2303表格标注\3、工具汇总\xllabelme.exe "xllabelme v5.1.7u.exe"
start C:\home\chenkunze\data\m2303表格标注\3、工具汇总
