title Éú³Éxllabelme.exe
call conda activate xllabelme

pyinstaller xllabelme.spec
ren dist\xllabelme.exe "xllabelme v5.1.7e.exe"
