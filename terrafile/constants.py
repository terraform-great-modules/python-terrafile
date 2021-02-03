"""Constants' definition"""
import re

REGISTRY_BASE_URL = 'https://registry.terraform.io/v1/modules'
GITHUB_DOWNLOAD_URL_RE = re.compile('https://[^/]+/repos/([^/]+)/([^/]+)/tarball/([^/]+)/.*')
