"""Install an isolated Finance add-on for the ORIGINAL menu. Does not touch private data."""
from pathlib import Path
from datetime import datetime
import os
import re
import shlex
import shutil
import sqlite3
import sys

MARKER='# Pocket Finance original-menu add-on'

def plan_install(package,home,prefix):
    menu=prefix/'bin/menu'
    if not menu.is_file():raise ValueError('Original menu was not found. This installer is for the original setup, not pocket.')
    command=prefix/'bin/finance'
    if command.exists() and MARKER not in command.read_text():raise ValueError('A different finance command already exists.')
    target=home/'bin/pocket-finance'
    for name in ['engine.py','main.py']:
        compile((package/name).read_text(),str(package/name),'exec')
    run='["python", str(Path.home() / "bin/pocket-finance/main.py")'
    changes=[]
    text=menu.read_text()
    if 'Pocket Finance' not in text:
        marker='        0)'
        if marker not in text or 'case ' not in text:raise ValueError('Menu layout differs. Existing files left unchanged.')
        used=[int(n) for n in re.findall(r'^\s*(\d+)\)',text,re.M)]
        number=max(used,default=0)+1
        lines=text.splitlines(keepends=True)
        prompt=next((i for i,l in enumerate(lines) if 'Choose:' in l),None)
        if prompt is None:raise ValueError('Menu prompt was not found.')
        lines.insert(prompt,f"    printf '\\033[1;32m{number}  Pocket Finance\\033[0m\\n'\n")
        text=''.join(lines).replace(marker,f'        {number})\n            python "$HOME/bin/pocket-finance/main.py"\n            ;;\n'+marker,1)
        text=re.sub(r'from 0 to \d+',f'from 0 to {number}',text)
        changes.append((menu,text))
    budget=home/'bin/budget.py'
    if budget.exists() and MARKER not in budget.read_text():
        wrapper=MARKER+'\nfrom pathlib import Path\nimport subprocess\nsubprocess.run('+run+'])\n'
        compile(wrapper,str(budget),'exec');changes.append((budget,wrapper))
    for name,functions in [('jabones.py',{'add_purchase':'--purchase','show_purchases':'--purchases'}),('organizer.py',{'correct_budget':'--correct','correct_purchase':'--correct'})]:
        path=home/'bin'/name
        if not path.exists():continue
        text=path.read_text()
        if MARKER in text:continue
        if 'actions = [' not in text:
            raise ValueError(f'{name} layout differs. Existing files left unchanged; share its current code for a compatible patch.')
        overrides='\n'+MARKER+'\n'
        for function,argument in functions.items():
            if f'def {function}(' not in text:raise ValueError(f'{function} not found. Existing files left unchanged.')
            overrides+=f'def {function}():\n    from pathlib import Path\n    subprocess.run({run}, {argument!r}])\n\n'
        updated=text.replace('actions = [',overrides+'actions = [',1)
        if 'import subprocess' not in text:updated='import subprocess\n'+updated
        compile(updated,str(path),'exec');changes.append((path,updated))
    return target,command,changes

def install(package,home,prefix):
    target,command,changes=plan_install(package,home,prefix)
    backup=home/'Everyday/Finance/Installer-Backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True)
    legacy=home/'Everyday/Jabones-Yayo/budget.sqlite'
    if legacy.exists():
        original=sqlite3.connect(legacy.resolve().as_uri()+'?mode=ro',uri=True);snapshot=sqlite3.connect(backup/'original-budget.sqlite')
        try:original.backup(snapshot)
        finally:original.close();snapshot.close()
    purchase=legacy.with_name('purchases.csv')
    if purchase.exists():shutil.copy2(purchase,backup/'original-purchases.csv')
    target.mkdir(parents=True,exist_ok=True)
    for name in ['engine.py','main.py']:
        installed=target/name
        if installed.exists():shutil.copy2(installed,backup/('previous-'+name))
        shutil.copy2(package/name,installed)
    if command.exists():shutil.copy2(command,backup/'finance-command')
    snapshots=[]
    for index,(path,text) in enumerate(changes):
        copy=backup/(str(index)+'-'+path.name);shutil.copy2(path,copy);snapshots.append((path,copy))
    try:
        for path,text in changes:
            pending=path.with_name(path.name+'.finance-installing')
            pending.write_text(text);pending.chmod(path.stat().st_mode & 0o777);pending.replace(path)
        command.parent.mkdir(parents=True,exist_ok=True)
        command.write_text('#!'+str(prefix/'bin/bash')+'\n'+MARKER+'\nexec '+shlex.quote(str(prefix/'bin/python'))+' '+shlex.quote(str(target/'main.py'))+' "$@"\n')
        command.chmod(0o700)
    except BaseException:
        for path,copy in snapshots:shutil.copy2(copy,path)
        raise
    print('Pocket Finance installed for your ORIGINAL menu.')
    print('Original databases and CSV files were preserved.')
    print('Previous scripts and source records backed up in:',backup)
    print('Run finance. First use option 12 to import your old records ONCE, then option 1 to create actual accounts.')
    print('Old budget/purchase/correction menu buttons now open Finance. The public pocket installation is unchanged.')

if __name__=='__main__':
    try:install(Path(__file__).resolve().parent,Path.home(),Path(os.environ['PREFIX']))
    except (ValueError,OSError,sqlite3.Error) as error:raise SystemExit(str(error))
