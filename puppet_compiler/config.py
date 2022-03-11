"""Module to hold config"""

from dataclasses import dataclass, fields
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

LOGGER = getLogger(__name__)


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
    puppet_netbox: Path = Path("/var/lib/catalog-differ/netbox-hiera")
    # Directory hosting all of puppet's runtime files usually
    # under /var/lib/puppet on debian-derivatives
    puppet_var: Path = Path("/var/lib/catalog-differ/puppet")
    pool_size: int = 2
    fail_fast: bool = False

    @classmethod
    def from_file(cls, configfile: Optional[Path], overrides: Dict[str, Any]) -> "ControllerConfig":
        try:
            data = yaml.safe_load(configfile.read_text()) if configfile is not None else {}

        except FileNotFoundError as error:
            LOGGER.exception("Configuration file %s is not a file: %s", configfile, error)
            data = {}

        except yaml.error.YAMLError as error:
            LOGGER.exception("Configuration file %s contains malformed yaml: %s", configfile, error)
            raise

        data.update(overrides)

        for key, value in data.items():
            if key not in dir(cls):
                raise Exception(f"Unknown config key {key}, known ones are: {fields(cls)}")

            expected_type = cls.__annotations__[key]
            try:
                # make sure to cast the strings to their annotated types
                data[key] = expected_type(value)

            except Exception as error:
                raise Exception(f"Bad value for key {key}, got {type(value)} expected {expected_type}.") from error

        return cls(**data)


# pylint: disable=too-many-instance-attributes
