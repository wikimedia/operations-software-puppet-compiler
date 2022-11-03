#!/usr/bin/python3
from pathlib import Path
from typing import List

from setuptools import find_packages, setup  # type: ignore

install_requires = ["cumin", "jinja2", "requests", "pyyaml"]
extras_require = {
    # Test dependencies
    "tests": [
        "bandit>=1.5.1",
        "flake8>=3.6.0",
        "mock",
        "mypy",
        "pytest",
        "pytest-cov",
        "requests_mock",
        "GitPython>=3.1.18",
        "black",
        "isort",
        "types-requests",
        "types-PyYAML",
        "types-mock",
        # This will not be needed once we move to python 3.8+
        # then we can use unittest.IsolatedAsyncioTestCase
        "aiounittest",
    ],
    "prospector": [
        "prospector[with_everything]>=0.12.4",
        "pytest>=3.10.1",
        "requests-mock>=1.5.2",
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
    version="2.5.0",
    description="Tools to compile puppet catalogs as a service",
    author="Joe",
    author_email="glavagetto@wikimedia.org",
    extras_require=extras_require,
    install_requires=install_requires,
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
