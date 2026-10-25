"""Non-destructive Termux installer; no shell profiles or existing menus edited."""
from pathlib import Path
import json
import os
import shlex
import shutil
import sys
from datetime import datetime

def install(package, home, prefix):
    app = home / '.local/share/pocket-toolbox'
    finance_files=['engine.py','main.py','charts.py','business_board.py','home_board.py','board_actions.py','finance_forms.py','board_server.py','pocket_security.py','cash_import.py','import_ui.py','statement_import.py']
    os.umask(0o077)
    compile((package/'src/app.py').read_text(),'app.py','exec')
    for name in finance_files:compile((package/'finance'/name).read_text(),name,'exec')
    command = prefix / 'bin/pocket'
    marker = '# Pocket Toolbox launcher'
    if command.exists() and marker not in command.read_text():
        raise RuntimeError('A different pocket command exists; rename it before installing.')
    sys.path.insert(0,str(package/'finance'))
    try:
        from pocket_security import harden_tree
        harden_tree(app)
    finally:sys.path.pop(0)
    target = app / 'app.py'
    if target.exists():
        shutil.copy2(target, app / ('app-before-update-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.py'))
    shutil.copy2(package / 'src/app.py', target)
    finance_target=app/'finance'
    finance_target.mkdir(exist_ok=True)
    finance_target.chmod(0o700)
    for name in finance_files:
        old=finance_target/name
        if old.exists():shutil.copy2(old,finance_target/(name+'.before-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')))
        shutil.copy2(package/'finance'/name,old)
    shutil.copy2(package/'finance/FINANCE.md',finance_target/'FINANCE.md')
    shutil.copy2(package/'finance/SECURITY.md',finance_target/'SECURITY.md')
    config = app / 'config.json'
    if not config.exists():
        template = package / 'config.json'
        if not template.exists():
            template = package / 'config.example.json'
        settings = json.loads(template.read_text())
        for key, label in [('title','Toolbox title'),('project_name','Project/business name'),
                           ('currency','Currency label'),('books_folder','Books folder')]:
            settings[key] = input(f'{label} [{settings[key]}]: ').strip() or settings[key]
        config.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + '\n')
    for name in ('README.md', 'CUSTOMIZE-ME.md','CHANGELOG.md','SUPPORT.md','LICENSE','SECURITY.md'):
        shutil.copy2(package / name, app / name)
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text('#!' + str(prefix / 'bin/bash') + '\n' + marker + '\nexec ' +
                       shlex.quote(str(prefix / 'bin/python')) + ' ' + shlex.quote(str(target)) + ' "$@"\n')
    command.chmod(0o700)
    print('\nInstalled. Type pocket to start. Existing menus and records were not imported.')
    print('For shared phone files, run termux-setup-storage and allow access.')

if __name__ == '__main__':
    install(Path(sys.argv[1]).resolve(), Path.home(), Path(os.environ['PREFIX']))
