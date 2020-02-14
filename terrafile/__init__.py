"""Locally download all modules"""
import os
import re
import shutil
import subprocess
import sys
import requests
import yaml
from .patch import Patch
from . import repository


REGISTRY_BASE_URL = 'https://registry.terraform.io/v1/modules'
GITHUB_DOWNLOAD_URL_RE = re.compile('https://[^/]+/repos/([^/]+)/([^/]+)/tarball/([^/]+)/.*')

# pylint: disable=missing-function-docstring
def get_source_from_registry(source, version):
    namespace, name, provider = source.split('/')
    registry_download_url = '{base_url}/{namespace}/{name}/{provider}/{version}/download'.format(
        base_url=REGISTRY_BASE_URL,
        namespace=namespace,
        name=name,
        provider=provider,
        version=version,
    )
    response = requests.get(registry_download_url)
    if response.status_code == 204:
        github_download_url = response.headers.get('X-Terraform-Get') or ''
        match = GITHUB_DOWNLOAD_URL_RE.match(github_download_url)
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


def get_terrafile_path(path):
    if os.path.isdir(path):
        return os.path.join(path, 'Terrafile')
    return path


def read_terrafile(path):
    try:
        with open(path) as open_file:
            terrafile = yaml.safe_load(open_file)
        if not terrafile:
            raise ValueError('{} is empty'.format(path))
    except IOError as error:
        sys.stderr.write('Error loading Terrafile: {}\n'.format(error.strerror))
        sys.exit(1)
    except ValueError as error:
        sys.stderr.write('Error loading Terrafile: {}\n'.format(error))
        sys.exit(1)
    else:
        return terrafile


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


def update_modules(path):
    terrafile_path = get_terrafile_path(path)
    module_path = os.path.dirname(terrafile_path)
    module_path_name = os.path.basename(os.path.abspath(module_path))

    terrafile = read_terrafile(terrafile_path)

    for name, repository_details in sorted(terrafile.items()):
        target = os.path.join(module_path, name)
        source = repository_details['source']

        # Support modules on the local filesystem.
        if source.startswith('./') or source.startswith('../') or source.startswith('/'):
            print('Copying {}/{}'.format(module_path_name, name))
            # Paths must be relative to the Terrafile directory.
            source = os.path.join(module_path, source)
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(source, target)
            continue

        version = repository_details['version']

        # Support Terraform Registry sources.
        if is_valid_registry_source(source):
            print('Checking {}/{}'.format(module_path_name, name))
            source, version = get_source_from_registry(source, version)

        # Skip this module if it has already been checked out.
        # This won't skip branches, because they may have changes
        # that need to be pulled.
        if has_git_tag(path=target, tag=version):
            print('Fetched {}/{}'.format(module_path_name, name))
            continue

        # add token to tthe source url if exists
        if 'GITHUB_TOKEN' in os.environ:
            source = add_github_token(source, os.getenv('GITHUB_TOKEN'))
        quilt = Patch(target)
        repo = repository.Repo(path=target, origin=source, version=version)
        # Delete the old directory and clone it from scratch.
        print('Fetching {}/{}'.format(module_path_name, name))
        shutil.rmtree(target, ignore_errors=True)
        output, returncode = repo.clone()
        if returncode != 0:
            sys.stderr.write(bytes.decode(output))
            sys.exit(returncode)
        patches = repository_details.get("patches", list())
        if patches:
            for i, patch in enumerate(repository_details.get("patches", list())):
                quilt.import_patch(name=f'patch_{i}.patch', content=patch)
            quilt.push_all()
