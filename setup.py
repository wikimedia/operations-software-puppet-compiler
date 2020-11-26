#!/usr/bin/python3
import os

from functools import reduce

from setuptools import find_packages, setup

install_requires = [
    'jinja2',
    'requests',
    'pyyaml'
]

extras_require = {
    # Test dependencies
    'tests': [
        'coverage',
        'bandit>=1.1.0',
        'flake8>=3.2.1',
        'prospector[with_everything]>=0.12.4,<=1.1.6.2',
        'mock<1.1.0',
        'nose',
        'requests_mock',
    ],
}


def all_files(cwd, path):
    return reduce(lambda x, y: x + y,
                  [[('%s/%s' % (x[0], y))[len(cwd) + 1:]
                    for y in x[2]] for x in os.walk(cwd + '/' + path)])


setup(
    name='puppet_compiler',
    version='1.0.0',
    description='Tools to compile puppet catalogs as a service',
    author='Joe',
    author_email='glavagetto@wikimedia.org',
    extras_require=extras_require,
    install_requires=install_requires,
    test_suite='nose.collector',
    zip_safe=True,
    packages=find_packages(),
    package_data={'puppet_compiler': all_files("puppet_compiler", "templates")},
    entry_points={
        'console_scripts': [
            'puppet-compiler = puppet_compiler.cli:main',
            'puppetdb-populate = puppet_compiler.populate_puppetdb:main',
            'pcc-debug-host = puppet_compiler.debug_host:main'
        ],
    },
)
