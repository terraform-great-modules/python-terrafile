"""Repository wrapper"""
import os
import subprocess

def run(*args, **kwargs):
    """Just a wrapper to subprocess"""
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
    stdout, stderr = proc.communicate()  # pylint: disable=unused-variable
    return (stdout, proc.returncode)

class Repo:
    """Abstract reporitory commands"""

    def __init__(self, path=None, origin=None, version=None):
        self._path = path
        self._origin = origin
        self._version = version
        self._uptodate = False

    def mkparentpath(self):
        """Parent folder is required for cloning!"""
        if not os.path.isdir(os.path.dirname(self.path)):
            os.mkdir(os.path.dirname(self.path))

    @property
    def path(self):
        """Local filesystem path"""
        return self._path

    @property
    def version(self):
        """Version to locally download"""
        return self._version

    @property
    def origin(self):
        """Upstream code source"""
        if not self._origin:
            if not self._path:
                raise SystemError('At least a local path or remote server is required')
            output, _ = run('git', 'remote', '-v', cwd=self.path)
            for line in output.split('\n'):
                if "origin" in line and "fetch" in line:
                    self._origin = line.split()[1]
                    break
            else:
                raise SystemError("No upstream repository is set")
        return self._origin

    @property
    def is_shallow(self):
        """Check if the repository is shallow (limited action)"""
        return os.path.isfile(os.path.join(self.path, ".git/shallow"))

    def run(self, *args, **kwargs):
        """Run command into path"""
        if 'cwd' not in kwargs:
            kwargs['cwd'] = self.path
        return run(*args, **kwargs)

    def clone(self, shallow=False):
        """Clone the repository"""
        if not self.path:
            self.path = self.origin.split("/")[-1]
            if self.path.endswith(".git"):
                self.path = self.path[:-4]
        if os.path.isdir(self.path):
            raise SystemError(f"Path {self.path} already exists, please delete it first")
        self.mkparentpath()
        if shallow:
            clone_args = ['git', 'clone', f'--branch={self.version}', '--depth 1',
                          '--single-branch', self.origin, self.path]
        else:
            clone_args = ['git', 'clone', f'--branch={self.version}', self.origin, self.path]
        output, returncode = run(*clone_args, cwd=os.path.dirname(self.path))
        self._uptodate = True
        return output, returncode

    def fetch(self):
        """Just fetch from upstream"""
        run('git', 'fetch', cwd=self.path)
        self._uptodate = True

    def list_origin_tags(self):
        """Show tags from origin"""
        if self.is_shallow:
            output, _ = run('git', 'ls-remote', self.origin)
        else:
            if not self._uptodate:
                self.fetch()
            output, _ = run('git', 'ls-remote', '.')
        tags = list()
        for line in output.splitlines():
            ref = line.splits()[1]
            if ref.startswith('refs/tags/'):
                tags.append(ref[10:])
        return tags
