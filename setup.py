#!/usr/bin/python
import os
from setuptools import setup, find_packages


def all_files(cwd, path):
    return reduce(lambda x, y: x + y,
                  [[('%s/%s' % (x[0], y))[len(cwd)+1:]
                    for y in x[2]] for x in os.walk(cwd + '/' + path)])


setup(
    name='puppet_compiler',
    version='0.0.1',
    description='Tools to compile puppet catalogs as a service',
    author='Joe',
    author_email='glavagetto@wikimedia.org',
    install_requires=['jinja2', 'requests', 'pyyaml'],
    test_suite='nose.collector',
    tests_require=['mock', 'nose'],
    zip_safe=True,
    packages=find_packages(),
    package_data={'puppet_compiler': all_files("puppet_compiler", "templates")},
    entry_points={
        'console_scripts': [
            'puppet-compiler = puppet_compiler.cli:main'
        ],
    },
)
