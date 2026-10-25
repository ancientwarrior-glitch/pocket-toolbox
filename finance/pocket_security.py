"""Private file handling and age-backed archive encryption; no custom cryptography."""
from contextlib import contextmanager
from pathlib import Path
import os
import secrets
import shutil
import stat
import subprocess
import tempfile

MAX_ARCHIVE_BYTES=512*1024*1024
MAX_MEMBER_BYTES=256*1024*1024
MAX_ARCHIVE_MEMBERS=10000


def private_umask():
    os.umask(0o077)


def no_links(path):
    path=Path(path).absolute()
    if any(p.is_symlink() for p in [path,*path.parents]):
        raise ValueError('Private records must not use symbolic links.')
    return path


def private_dir(path):
    private_umask();path=no_links(path)
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    path.chmod(0o700)
    if stat.S_IMODE(path.stat().st_mode)&0o077:
        raise ValueError('This location cannot enforce private permissions. Keep records in Termux internal storage.')
    return path


def private_file(path):
    path=no_links(path)
    if path.exists():
        if not path.is_file():raise ValueError('Expected a regular private file.')
        path.chmod(0o600)
        if stat.S_IMODE(path.stat().st_mode)&0o077:raise ValueError('Cannot make record file private.')
    return path


def harden_tree(root):
    root=private_dir(root)
    for directory,dirs,files in os.walk(root,followlinks=False):
        private_dir(directory)
        for name in dirs:no_links(Path(directory)/name)
        for name in files:private_file(Path(directory)/name)


def age_binary():
    binary=shutil.which('age')
    if not binary:raise ValueError('Encrypted backups need age. Run: pkg install age. No plaintext backup was exported.')
    return binary


def clean_env():
    env=os.environ.copy()
    # Passphrases must be entered into age's terminal prompt, never inherited.
    env.pop('AGE_PASSPHRASE',None)
    return env


def encrypt_archive(source,destination):
    binary=age_binary();private_umask()
    source=private_file(source);destination=Path(destination)
    if source.stat().st_size>MAX_ARCHIVE_BYTES:raise ValueError("Backup exceeds the supported archive size limit.")
    if destination.exists():raise ValueError('Backup destination already exists.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    partial=destination.with_name('.'+destination.name+'.'+secrets.token_hex(8)+'.partial')
    try:
        with partial.open('xb') as output:
            result=subprocess.run([binary,'--passphrase',str(source)],stdout=output,env=clean_env(),check=False)
            output.flush();os.fsync(output.fileno())
        if result.returncode:raise ValueError('Backup encryption did not finish. No backup was published.')
        if not partial.stat().st_size:raise ValueError('Encryption produced no output.')
        os.replace(partial,destination)
        return destination
    finally:partial.unlink(missing_ok=True)


@contextmanager
def decrypted_archive(source,private_root):
    source=Path(source)
    if not source.name.endswith('.age'):
        yield source;return
    binary=age_binary()
    with tempfile.TemporaryDirectory(prefix='.restore-',dir=private_dir(private_root)) as folder:
        output=Path(folder)/'archive.tar.gz'
        process=None
        try:
            with output.open('xb') as stream:
                process=subprocess.Popen([binary,'--decrypt',str(source)],stdout=subprocess.PIPE,env=clean_env())
                size=0
                while True:
                    chunk=process.stdout.read(1024*1024)
                    if not chunk:break
                    size+=len(chunk)
                    if size>MAX_ARCHIVE_BYTES:raise ValueError('Decrypted archive exceeds the size limit.')
                    stream.write(chunk)
            if process.wait():raise ValueError('Decryption failed: wrong passphrase, damaged backup or cancelled prompt. Records were not restored.')
            yield output
        finally:
            if process:
                if process.poll() is None:process.terminate()
                process.wait()
                if process.stdout:process.stdout.close()
