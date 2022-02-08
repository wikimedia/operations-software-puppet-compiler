"""Collections of helpers"""
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from puppet_compiler import _log


def construct_ruby_object(loader, _suffix, node):
    """YAML construct to map object to dict."""
    return loader.construct_yaml_map(node)


class FactsFileNotFound(Exception):
    """Exception for missing facts files"""


def facts_file(vardir: Path, hostname: str) -> Path:
    """Finds facts file for the given hostname.

    Search subdirs recursively.  If we find multiple matches, return the newest one.

    Arguments:
        vardir: The directory to search
        hostname: The hostname to search for

    """
    try:
        # try to get the most recent fact file based on the file mtime
        return sorted(
            (vardir / "yaml").glob(f"**/facts/{hostname}.yaml"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )[0]
    except IndexError as error:
        raise FactsFileNotFound(f"Unable to find fact file for: {hostname} under directory {vardir}") from error


def refresh_yaml_date(facts_path: Path) -> None:
    """Refresh the timestamp and the expiration of the yaml facts cache.

    This avoids incurring https://tickets.puppetlabs.com/browse/PUP-5441
    when using puppetdb.

    Arguments:
        facts_path: The path to the facts file to refresh
    """
    yaml.add_multi_constructor("!ruby/object:", construct_ruby_object)
    date_format = "%Y-%m-%d %H:%M:%S.%s +00:00"
    _log.debug("Patching %s", facts_path)
    datetime_facts = datetime.utcnow()
    datetime_exp = datetime_facts + timedelta(days=1)
    data = yaml.load(facts_path.read_text(), Loader=yaml.Loader)
    data["expiration"] = datetime_exp.strftime(date_format)
    data["timestamp"] = datetime_facts.strftime(date_format)
    tmp_facts_path = facts_path.parent / (facts_path.name + ".tmp")
    new_content = "--- !ruby/object:Puppet::Node::Facts\n" + yaml.safe_dump(data)
    tmp_facts_path.write_text(new_content)
    # TODO: in python 3.7 theses move expects a str
    shutil.move(str(tmp_facts_path), str(facts_path))
