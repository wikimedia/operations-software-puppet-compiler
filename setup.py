#!/usr/bin/python3
from pathlib import Path
from typing import List

from setuptools import find_packages, setup

install_requires = ["cumin", "jinja2", "requests", "pyyaml"]
extras_require = {
    # Test dependencies
    "tests": [
        "coverage",
        "bandit>=1.5.1",
        "flake8>=3.6.0",
        "prospector[with_everything]>=1.4.1",
        "mock",
        "nose",
        "requests_mock",
        "GitPython>=3.1.18",
        "black",
        "isort",
        "types-requests",
        "types-PyYAML",
        "types-mock",
    ],
}


def get_templates() -> List[str]:
    """Return the list of templates."""
    project_path = Path("./puppet_compiler")
    return [
        str(template_path.relative_to(project_path)) for template_path in project_path.glob("templates/**/*.jinja2")
    ]


setup(
    name="puppet_compiler",
    version="1.2.0",
    description="Tools to compile puppet catalogs as a service",
    author="Joe",
    author_email="glavagetto@wikimedia.org",
    extras_require=extras_require,
    install_requires=install_requires,
    test_suite="nose.collector",
    zip_safe=True,
    packages=find_packages(),
    package_data={"puppet_compiler": get_templates()},
    entry_points={
        "console_scripts": [
            "puppet-compiler = puppet_compiler.cli:main",
            "puppetdb-populate = puppet_compiler.populate_puppetdb:main",
            "pcc-debug-host = puppet_compiler.debug_host:main",
        ],
    },
)
