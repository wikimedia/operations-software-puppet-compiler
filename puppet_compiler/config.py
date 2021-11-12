"""Module to hold config"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ControllerConfig:
    """Class to hold controller config"""

    # Url under which results will be found
    http_url: str = "https://puppet-compiler.wmflabs.org/html"
    # Base working directory of the compiler
    base: Path = Path("/mnt/jenkins-workspace")
    # Location (either on disk, or at a remote HTTP location)
    # of the operations/puppet repository
    puppet_src: Path = Path("/var/lib/catalog-differ/production")
    # Location (either on disk, or at a remote HTTP location)
    # of the labs/private repository
    puppet_private: Path = Path("/var/lib/catalog-differ/private")
    # Directory hosting all of puppet's runtime files usually
    # under /var/lib/puppet on debian-derivatives
    puppet_var: Path = Path("/var/lib/catalog-differ/puppet")
    pool_size: int = 2
