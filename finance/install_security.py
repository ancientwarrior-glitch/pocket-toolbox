"""Patch supported local scripts without uploading or embedding their private paths."""
from pathlib import Path
from datetime import datetime
import ast
import importlib.util
import os
import re
import shutil
import sys
from pocket_security import private_dir,harden_tree,private_umask,no_links

MARKER='# Pocket local security update 0.2.1'
FILES=['engine.py','charts.py','board_server.py','pocket_security.py','secure_backup.py','secure_compat.py']

def patch_main(text):
    if MARKER in text:
        text=text.replace("('Encrypted full toolbox backup',self.secure_backup)",
                          "('Encrypted backups: create, verify and share',self.secure_backup)")
        compile(text,'main.py','exec');return text
    tree=ast.parse(text)
    cls=next((n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='UI'),None)
    method=next((n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='main'),None) if cls else None
    assignments=[n for n in ast.walk(method) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='actions' for t in n.targets) and isinstance(n.value,ast.List)] if method else []
    if len(assignments)!=1:raise ValueError('Unsupported local menu layout. No scripts were changed.')
    lines=text.splitlines(keepends=True);assignment=assignments[0]
    indent=re.match(r'\s*',lines[assignment.lineno-1])[0]
    lines.insert(assignment.end_lineno,indent+"actions.extend([('Encrypted backups: create, verify and share',self.secure_backup),('Restore encrypted full toolbox backup',self.secure_restore)])\n")
    text=''.join(lines)
    match=re.search(r'^if __name__\s*==',text,re.M)
    if not match:raise ValueError('Local entry point was not recognized. No scripts were changed.')
    text=text[:match.start()]+MARKER+'\nfrom secure_compat import enhance_ui\nenhance_ui(UI)\n\n'+text[match.start():]
    text=text.replace("Path.home()/'storage/downloads/Finance-Reports'","self.root/'Exports'")
    compile(text,'main.py','exec');return text

def patch_actions(text):
    if 'from pocket_security import no_links,private_dir' in text:return text
    text='from pocket_security import no_links,private_dir\n'+text
    text=text.replace("        path = self.organizer / (kind + '.json')","        path = self.organizer / (kind + '.json')\n        no_links(path)")
    text=text.replace('        path.parent.mkdir(parents=True, exist_ok=True)','        private_dir(path.parent)').replace('        backups.mkdir(exist_ok=True)','        private_dir(backups)')
    text=text.replace('                folder.mkdir(parents=True, exist_ok=True)','                private_dir(folder)')
    text=text.replace("                path = folder / ('board-' + request_id + '.txt')","                path = folder / ('board-' + request_id + '.txt')\n                no_links(path)")
    compile(text,'board_actions.py','exec');return text

def patch_shell(text):
    for number,action in [(5,'backup'),(13,'restore')]:
        if 'secure_compat.py" '+action in text:continue
        match=re.search(rf'(?m)^([ \t]*){number}\)[^\n]*;;[ \t]*$',text)
        if not match:match=re.search(rf'(?ms)^([ \t]*){number}\)[^\n]*\n(?:(?!^[ \t]*(?:\d+|\*)\)|^[ \t]*esac\b).)*?^[ \t]*;;[ \t]*$',text)
        if match and not re.search(r'\b(?:case|esac)\b',match[0]):
            indent=match[1];replacement=indent+str(number)+')\n'+indent+'    python "$HOME/bin/pocket-finance/secure_compat.py" '+action+'\n'+indent+'    ;;'
            text=text[:match.start()]+replacement+text[match.end():]
    return text

def install(package,home,prefix):
    private_umask();package=Path(package);home=Path(home);prefix=Path(prefix)
    target=no_links(home/'bin/pocket-finance');main=target/'main.py'
    if not main.is_file():raise ValueError('An existing original Finance installation was not found. Public pocket users use install.sh instead.')
    for name in FILES:compile((package/name).read_text(),name,'exec')
    updates={main:patch_main(main.read_text())}
    actions=target/'board_actions.py'
    if actions.exists():updates[actions]=patch_actions(actions.read_text())
    board=target/'home_board.py'
    if board.exists():updates[board]=board.read_text().replace("path.name.endswith('.tar.gz')","path.name.endswith(('.tar.gz','.tar.gz.age'))")
    menu=no_links(prefix/'bin/menu')
    if menu.exists():updates[menu]=patch_shell(menu.read_text())
    # Obtain the already installed data root locally. Its value is never sent anywhere.
    sys.path.insert(0,str(target))
    try:
        spec=importlib.util.spec_from_file_location('pocket_existing_ui',main);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        ui=module.UI();record_root=ui.root
        ui.f.close()
    finally:sys.path.pop(0)
    harden_tree(record_root.parent)
    private_dir(target)
    backup=private_dir(record_root/'Installer-Backups'/('security-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')))
    snapshots=[]
    for index,path in enumerate([*updates,*[target/name for name in FILES]]):
        if path.exists():
            no_links(path);copy=backup/(str(index)+'-'+path.name);shutil.copy2(path,copy);snapshots.append((path,copy))
    try:
        for name in FILES:shutil.copy2(package/name,target/name)
        shutil.copy2(package/'SECURITY.md',target/'SECURITY.md')
        for path,text in updates.items():
            mode=path.stat().st_mode&0o700
            pending=path.with_name(path.name+'.security-pending');no_links(pending)
            pending.write_text(text);pending.chmod(mode or 0o600);pending.replace(path)
    except BaseException:
        for path,copy in snapshots:shutil.copy2(copy,path)
        raise
    print('Local security update installed. Records were not uploaded or imported.')
    print('Previous scripts saved privately:',backup)
    print('Run: pkg install age. Restart menu. Finance option 21 opens Create / Verify / Share / Show folder; option 22 restores.')
    print('Recognized backup buttons are redirected. Unknown shell layouts remain unchanged; use the Finance options.')

if __name__=='__main__':
    try:install(Path(__file__).resolve().parent,Path.home(),Path(os.environ['PREFIX']))
    except (ValueError,OSError) as error:raise SystemExit(str(error))
