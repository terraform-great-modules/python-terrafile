#!/usr/bin/env python

from setuptools import setup

setup(
    name='terrafile',
    version='0.4.2',
    description='Manages external Terraform modules.',
    author='Riccardo Scartozzi Raymond Butcher',
    author_email='ray.butcher@claranet.uk',
    url='https://github.com/claranet/python-terrafile',
    license='MIT License',
    packages=(
        'terrafile',
    ),
    scripts=(
        'bin/pterrafile',
    ),
    install_requires=(
        'pyyaml',
        'requests',
    ),
)
