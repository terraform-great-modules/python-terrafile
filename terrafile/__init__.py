"""Locally download all modules"""
import os
import re
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import yaml
from .patch import Patch
from . import repository
from . import constants


# pylint: disable=missing-function-docstring
def get_source_from_registry(source, version):
    namespace, name, provider = source.split('/')
    registry_download_url = '{base_url}/{namespace}/{name}/{provider}/{version}/download'.format(
        base_url=constants.REGISTRY_BASE_URL,
        namespace=namespace,
        name=name,
        provider=provider,
        version=version,
    )
    response = requests.get(registry_download_url)
    if response.status_code == 204:
        github_download_url = response.headers.get('X-Terraform-Get') or ''
        match = constants.GITHUB_DOWNLOAD_URL_RE.match(github_download_url)
        if match:
            user, repo, version = match.groups()
            source = 'https://github.com/{}/{}.git'.format(user, repo)
            return source, version
    sys.stderr.write('Error looking up module in Terraform Registry: {}\n'.format(response.content))
    sys.exit(1)


def add_github_token(github_download_url, token):
    github_repo_url_pattern = re.compile('.*github.com/(.*)/(.*)\.git')  # pylint: disable=anomalous-backslash-in-string
    match = github_repo_url_pattern.match(github_download_url)
    url = github_download_url
    if match:
        user, repo = match.groups()
        url = 'https://{}@github.com/{}/{}.git'.format(token, user, repo)
    return url


def run(*args, **kwargs):
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
    stdout, stderr = proc.communicate()  # pylint: disable=unused-variable
    return (stdout, proc.returncode)


def has_git_tag(path, tag):
    tags = set()
    if os.path.isdir(path):
        output, returncode = run('git', 'tag', '--points-at=HEAD', cwd=path)
        if returncode == 0:
            tags.update([t.decode('utf-8') for t in output.split()])
    return tag in tags


def is_valid_registry_source(source):
    # pylint: disable=duplicate-string-formatting-argument,line-too-long
    name_sub_regex = '[0-9A-Za-z](?:[0-9A-Za-z-_]{0,62}[0-9A-Za-z])?'
    provider_sub_regex = '[0-9a-z]{1,64}'
    registry_regex = re.compile('^({})\\/({})\\/({})(?:\\/\\/(.*))?$'.format(name_sub_regex, name_sub_regex, provider_sub_regex))
    if registry_regex.match(source):
        return True
    return False


class Terrafile:
    """A wrapper to git and quilt for local dependency management.
    As possible, commands are run in parallel.
    """
    CONF_FILE = 'Terrafile'

    def __init__(self, cwd=None):
        self._config = None
        self._modules = None
        self.get_config(cwd)

    @property
    def config(self):
        """Terrafile configuration"""
        return self._config

    @property
    def modules(self):
        """Terrafile modules list"""
        return self._modules

    @property
    def module_path(self):
        """Modules are expected to be saved in the same folder of file configuration"""
        return self.config['cwd']

    @property
    def num_worker(self):
        """Number of concurrent thread"""
        return self.config.get("jobs", 4)

    def get_config(self, cwd):
        """Find project folder and load configuration"""
        path = Path(cwd) if cwd else Path.cwd()
        if path.is_file():
            conf_file = path
            cwd = path.parent
        else:  # Do a reverse search on parent folders
            for _ in range(0, 4):
                if not os.path.isdir(path):
                    raise ValueError(f'Path "{path}" is not a folder')
                if (path / self.CONF_FILE).is_file():
                    break
                path = path.parent
            else:
                raise ValueError(f"Not found any {self.CONF_FILE} under {path}")
            conf_file = path / self.CONF_FILE
            cwd = path
        try:
            with open(conf_file) as open_file:
                terrafile = yaml.safe_load(open_file)
            if not terrafile:
                raise ValueError('{} is empty'.format(path))
        except IOError as error:
            sys.stderr.write('Error loading Terrafile: {}\n'.format(error.strerror))
            sys.exit(1)
        except ValueError as error:
            sys.stderr.write('Error loading Terrafile: {}\n'.format(error))
            sys.exit(1)
        config = terrafile.pop('setup', dict())
        config['cwd'] = cwd
        self._config = config
        self._modules = terrafile

    def update_repos(self):
        """Try to update all repositories"""
        errors = False
        with ThreadPoolExecutor(max_workers=self.num_worker) as executor:
            future_to_update = {
                executor.submit(update_module, self.module_path, name, setup): name \
                for name, setup in sorted(self.modules.items())}
            for future in as_completed(future_to_update):
                module = future_to_update[future]
                try:
                    future.result()
                except Exception as exc:  # pylint: disable=broad-except
                    tb_str = traceback.format_exception(etype=type(exc), value=exc,
                             tb=exc.__traceback__)
                    print('%r generated an exception: %s\nTrace: %s' % (module, exc, tb_str))
                    errors = True
                else:
                    print('%r is updated' % (module))
        if errors:
            raise SystemError("Module update error!")
        return True


    def patch_repos(self):
        """Try to apply provided quilt patches"""

    def run(self):
        """Try to fetch all configuration repositories"""
        self.update_repos()


def update_module(cwd, name, conf):
    """Update the named module, under the provided cwd, with the given conf"""
    target = cwd / name
    source = conf['source']

    # Support modules on the local filesystem.
    if source.startswith('./') or source.startswith('../') or source.startswith('/'):
        print('Copying {}/{}'.format(cwd, name))
        # Paths must be relative to the Terrafile directory.
        source = cwd / source
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(source, target)
        return

    version = conf['version']
    # Support Terraform Registry sources.
    if is_valid_registry_source(source):
        print('Checking {}/{}'.format(cwd, name))
        source, version = get_source_from_registry(source, version)

    # add token to the source url if exists
    if 'GITHUB_TOKEN' in os.environ:
        source = add_github_token(source, os.getenv('GITHUB_TOKEN'))
    # Delete the old directory and clone it from scratch.
    print('Fetching {}'.format(target))
    shutil.rmtree(target, ignore_errors=True)
    repo = repository.Repo(path=target, origin=source, version=version)
    output, returncode = repo.clone()
    if returncode != 0:
        sys.stderr.write(bytes.decode(output))
        sys.exit(returncode)
    if conf.get("patches") or conf.get("patches_file"):
        quilt = Patch(target, root=cwd)
        i = 0
        for i, patch in enumerate(conf.get("patches", list())):
            quilt.import_patch(name=f'patch_{i}.patch', content=patch)
        for i, patch in enumerate(conf.get("patches_file", list()), start=i+1):
            quilt.import_patch(name=f'patch_{i}.patch', file_path=patch)
        status = quilt.push_all()
        if status != 0:
            raise SystemError("Error to push patches")


def main(path=None):
    """CLI entry point"""
    terrafile = Terrafile(path)
    try:
        terrafile.run()
    except Exception:  # pylint: disable=broad-except
        sys.exit(1)
