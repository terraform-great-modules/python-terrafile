"""Manage patches"""
import os
import subprocess
from tempfile import NamedTemporaryFile
from pathlib import Path


class Patch:
    """Quilt interface"""

    def __init__(self, path, root=None):
        self.path = path
        self.root = root
        self._is_init = False

    def run(self, *args, **kwargs):
        """Run command into path"""
        if 'cwd' not in kwargs:
            kwargs['cwd'] = self.path
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
        stdout, _ = proc.communicate()
        return (stdout, proc.returncode)

    def init(self):
        """Initialize patch folder"""
        if not os.path.isdir(os.path.join(self.path, 'patches')):
            os.mkdir(os.path.join(self.path, 'patches'))
        self.run('quilt', 'init')
        self._is_init = True

    @property
    def series(self):
        """List of current patches"""
        output, _ = self.run('quilt', 'series')
        return output.splitlines()

    def pop_all(self):
        """Pop all patches"""
        _, _rc = self.run('quilt', 'pop', '-a')
        return _rc

    def push_all(self):
        """Push all patches"""
        _, _rc = self.run('quilt', 'push', '-a')
        return _rc

    def import_patch(self, name='patch', file_path=None, content=None):
        """Import the patch from a filepath, or from content"""
        cmd = ['quilt', 'import', '-P', name]
        if file_path and content:
            raise ValueError("Provide only a file_path or a content")
        if file_path:
            file_path = Path(self.root) / file_path
            if not file_path.exists():
                raise ValueError(f"Not found patch file {file_path}")
            cmd.append(file_path)
            stdout, status = self.run(*cmd)
        elif content:
            with NamedTemporaryFile() as tmp:
                tmp.write(content.encode())
                tmp.write('\n'.encode())
                tmp.flush()
                cmd.append(tmp.name)
                stdout, status = self.run(*cmd)
        else:
            raise ValueError("A file_path or a content is required")
        if status != 0:
            print("Error to apply path!")
            print(f"Error message: {stdout}")
            raise SystemError("Error running quilt")

    def diff_patch(self, from_local, file_path=None, content=None):
        """Diff of local with remote patch"""
