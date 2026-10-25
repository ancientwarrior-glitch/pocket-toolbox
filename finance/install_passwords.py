"""Install the interface password gate on supported original toolbox entry points.

Never migrates/deletes/encrypts working records. Copies stay on the phone.
"""
from pathlib import Path
import ast
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pocket_security import private_dir,no_links
from app_lock import MARKER

KNOWN={'pocket','menu','finance','rss','books','book','everyday','jabones','budget','organizer','toolbox-home','dashboard'}

def python_guard(text):
    if MARKER in text:return text
    tree=ast.parse(text);line=0
    for i,node in enumerate(tree.body):
        if i==0 and isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str) or isinstance(node,ast.ImportFrom) and node.module=='__future__':line=node.end_lineno
        else:break
    lines=text.splitlines(keepends=True)
    if not line and lines and lines[0].startswith('#!'):line=1
    block=(MARKER+'\nif __name__ == "__main__":\n'
           '    import sys as _pocket_lock_sys\n    from pathlib import Path as _PocketLockPath\n'
           '    _pocket_lock_sys.path.insert(0, str(_PocketLockPath.home()/".local/share/pocket-toolbox-security"))\n'
           '    from app_lock import guard as _pocket_password_guard\n    _pocket_password_guard()\n\n')
    lines.insert(line,block);result=''.join(lines);compile(result,'guarded.py','exec');return result

def shell_guard(text,home,prefix):
    if MARKER in text:return text
    script=home/'.local/share/pocket-toolbox-security/app_lock.py'
    py=shlex.quote(str(prefix/'bin/python'));gate=shlex.quote(str(script));shell=shlex.quote(str(prefix/'bin/bash'))
    block=(MARKER+'\n'+py+' '+gate+' --check || exec '+py+' '+gate+' -- '+shell+' "$0" "$@"\n')
    lines=text.splitlines(keepends=True);lines.insert(1 if lines and lines[0].startswith('#!') else 0,block);return ''.join(lines)

def install(package,home,prefix):
    package,home,prefix=map(Path,(package,home,prefix))
    source=package/'app_lock.py';compile(source.read_text(),'app_lock.py','exec')
    candidates=[]
    for base in [home/'bin',prefix/'bin']:
        if base.is_dir():
            for path in base.iterdir():
                if path.is_file() and (path.stem in KNOWN or base==home/'bin' and path.suffix=='.py'):candidates.append(path)
    target=home/'bin/pocket-finance/main.py'
    if target.is_file():candidates.append(target)
    for base in [home/'.shortcuts',home/'.shortcuts/tasks']:
        if base.is_dir():candidates.extend(p for p in base.iterdir() if p.is_file() and not p.name.startswith('.'))
    updates={};skipped=[]
    for path in sorted(set(candidates)):
        no_links(path)
        try:text=path.read_text()
        except UnicodeError:skipped.append(str(path));continue
        if MARKER in text:continue
        first=text.splitlines()[0] if text else ''
        if path.suffix=='.py' or 'python' in first:result=python_guard(text)
        elif 'sh' in first or path.name in KNOWN or path.parent.name in ('.shortcuts','tasks'):
            result=shell_guard(text,home,prefix)
            checked=subprocess.run([str(prefix/'bin/bash'),'-n'],input=result,text=True,capture_output=True)
            if checked.returncode:skipped.append(str(path));continue
        else:skipped.append(str(path));continue
        updates[path]=result
    board=home/'bin/pocket-finance/board_server.py'
    if board.is_file():
        no_links(board);text=(package/'board_server.py').read_text();compile(text,'board_server.py','exec');updates[board]=text
    if not updates and not target.exists() and not (prefix/'bin/menu').exists():raise ValueError('Original toolbox not found. Public pocket users update using install.sh.')
    security=private_dir(home/'.local/share/pocket-toolbox-security')
    backup=private_dir(security/'Installer-Backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    snapshots=[];created=[]
    for i,path in enumerate(updates):
        snapshot=backup/(str(i)+'-'+path.name);shutil.copy2(path,snapshot);snapshots.append((path,snapshot))
    for name in ['app_lock.py','pocket_security.py']:
        path=security/name
        if path.exists():
            no_links(path);snapshot=backup/('runtime-'+name);shutil.copy2(path,snapshot);snapshots.append((path,snapshot))
        else:created.append(path)
    try:
        for name in ['app_lock.py','pocket_security.py']:shutil.copy2(package/name,security/name)
        for path,text in updates.items():
            pending=no_links(path.with_name(path.name+'.password-pending'));pending.write_text(text);pending.chmod(path.stat().st_mode&0o700 or 0o600);pending.replace(path)
        for name,argument in [('pocket-lock','--lock'),('pocket-password','--settings')]:
            path=no_links(prefix/'bin'/name)
            if path.exists() and MARKER not in path.read_text():raise ValueError('Unrelated command already exists: '+name)
            if path.exists():
                snapshot=backup/name;shutil.copy2(path,snapshot);snapshots.append((path,snapshot))
            else:created.append(path)
            path.write_text('#!'+str(prefix/'bin/bash')+'\n'+MARKER+'\nexec '+shlex.quote(str(prefix/'bin/python'))+' '+shlex.quote(str(security/'app_lock.py'))+' '+argument+'\n');path.chmod(0o700)
    except BaseException:
        for path,snapshot in reversed(snapshots):shutil.copy2(snapshot,path)
        for path in created:path.unlink(missing_ok=True)
        raise
    print('Password interface lock installed. Next toolbox opening asks you to create a NEW toolbox password.')
    print('Close every old toolbox/board session before opening the widget again.')
    print('Exit or Ctrl+] locks; 5 minutes without terminal input or board loading/saving also locks.')
    print('pocket-lock locks the active session; pocket-password changes its password after verifying the current one.')
    print('Working files have NOT been encrypted. This is an interface lock, not protection against shell access.')
    print('Backup passwords are unchanged. Local previous scripts:',backup)
    print('Guarded entry points:',len(updates))
    if skipped:print('Unrecognized entries (not edited):',', '.join(skipped))

if __name__=='__main__':
    try:install(Path(__file__).resolve().parent,Path.home(),Path(os.environ['PREFIX']))
    except (ValueError,OSError,SyntaxError) as e:raise SystemExit(str(e))
