"""Encrypted bundles for explicitly selected private toolbox roots."""
from pathlib import Path,PurePosixPath
from contextlib import closing
from datetime import datetime
import io
import json
import os
import secrets
import shutil
import sqlite3
import tarfile
import tempfile
from pocket_security import private_dir,no_links,encrypt_archive,decrypted_archive,MAX_MEMBER_BYTES,MAX_ARCHIVE_BYTES,MAX_ARCHIVE_MEMBERS


def backup_bundle(roots,private_root,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    target=folder/('toolbox-private-'+datetime.now().strftime('%Y%m%d-%H%M%S-')+secrets.token_hex(4)+'.tar.gz.age')
    with tempfile.TemporaryDirectory(prefix='.bundle-',dir=private_dir(private_root)) as temporary:
        temporary=Path(temporary);plain=temporary/'bundle.tar.gz'
        count=1;expanded=0
        def check_member(info):
            nonlocal count,expanded
            count+=1;expanded+=info.size
            if count>MAX_ARCHIVE_MEMBERS or info.size>MAX_MEMBER_BYTES or expanded>MAX_ARCHIVE_BYTES:raise ValueError('Records exceed safe backup/restore limits.')
            info.mode=0o700 if info.mode&0o100 else 0o600
            return info
        with tarfile.open(plain,'w:gz') as out:
            manifest=json.dumps({'format':'pocket-private-bundle-v1','roots':sorted(roots)}).encode()
            info=tarfile.TarInfo('bundle.json');info.size=len(manifest);info.mode=0o600;out.addfile(info,io.BytesIO(manifest))
            for key,root in roots.items():
                if not key.isalpha():raise ValueError('Invalid bundle root.')
                root=no_links(root)
                if not root.exists():continue
                files=sorted(root.rglob('*')) if root.is_dir() else [root]
                for path in files:
                    if path.is_relative_to(temporary) or '__pycache__' in path.parts:continue
                    no_links(path)
                    if not path.is_file() or any(path.name.endswith(s) for s in ('.sqlite-wal','.sqlite-shm','.sqlite-journal','.db-wal','.db-shm','.db-journal')):continue
                    name=key+'/'+str(path.relative_to(root)) if root.is_dir() else key
                    with path.open('rb') as probe:sqlite_header=probe.read(16)==b'SQLite format 3\x00'
                    if sqlite_header:
                        snapshot=temporary/(secrets.token_hex(8)+'.sqlite')
                        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(snapshot)) as dest:source.backup(dest)
                        out.add(snapshot,arcname=name,recursive=False,filter=check_member)
                    else:out.add(path,arcname=name,recursive=False,filter=check_member)
        encrypt_archive(plain,target)
    return target


def restore_bundle(archive,roots,private_root,backup_folder,confirm=input):
    with decrypted_archive(archive,private_root) as plain,tempfile.TemporaryDirectory(prefix='.bundle-restore-',dir=private_dir(private_root)) as temporary:
        temporary=Path(temporary);staged=[];seen=set();manifest=None;size=0
        with tarfile.open(plain,'r:gz') as source:
            for index,member in enumerate(source):
                size+=member.size
                if index>=MAX_ARCHIVE_MEMBERS or member.size<0 or member.size>MAX_MEMBER_BYTES or size>MAX_ARCHIVE_BYTES:raise ValueError('Bundle exceeds safe restore limits.')
                name=PurePosixPath(member.name)
                if name.is_absolute() or '..' in name.parts or not member.isfile() or str(name) in seen:raise ValueError('Unsafe bundle member.')
                seen.add(str(name))
                target=temporary/str(index)
                with source.extractfile(member) as inp,target.open('xb') as out:shutil.copyfileobj(inp,out)
                if target.stat().st_size!=member.size:raise ValueError('Truncated bundle.')
                if str(name)=='bundle.json':manifest=json.loads(target.read_text());continue
                if not name.parts or name.parts[0] not in roots:raise ValueError('Unknown bundle root.')
                root=no_links(roots[name.parts[0]])
                # Mapped file roots are explicit; other roots are directories.
                if len(name.parts)==1:
                    if root.exists() and root.is_dir():raise ValueError('Root type mismatch.')
                    dest=root
                else:
                    if root.exists() and root.is_file():raise ValueError('Root type mismatch.')
                    dest=root.joinpath(*name.parts[1:])
                no_links(dest)
                if dest.suffix=='.sqlite':
                    with closing(sqlite3.connect(target.as_uri()+'?mode=ro',uri=True)) as db:
                        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Invalid database in bundle.')
                staged.append((target,dest,0o700 if member.mode&0o100 else 0o600))
        if not isinstance(manifest,dict) or manifest.get('format')!='pocket-private-bundle-v1' or set(manifest.get('roots',[]))!=set(roots):raise ValueError('Incompatible bundle.')
        if confirm('Type RESTORE to replace matching files (extra files remain): ')!='RESTORE':return None
        before=backup_bundle(roots,private_root,backup_folder)
        for source,dest,mode in staged:
            private_dir(dest.parent);no_links(dest)
            fd,pending=tempfile.mkstemp(prefix='.restoring-',dir=dest.parent)
            try:
                with os.fdopen(fd,'wb') as out,source.open('rb') as inp:shutil.copyfileobj(inp,out)
                Path(pending).chmod(mode);os.replace(pending,dest)
            finally:Path(pending).unlink(missing_ok=True)
        return before
