"""Collections of helpers"""
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from puppet_compiler import _log


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
    # No, we cannot read the yaml. It contains ruby data structures.
    date_format = "%Y-%m-%d %H:%M:%S.%s +00:00"
    _log.debug("Patching %s", facts_path)
    ts_re = r"(\s+\"_timestamp\":) .*"
    exp_re = r"(\s+expiration:) .*"
    datetime_facts = datetime.utcnow()
    datetime_exp = datetime_facts + timedelta(days=1)
    ts_sub = f"\\1 {datetime_facts.strftime(date_format)}"
    exp_sub = f"\\1 {datetime_exp.strftime(date_format)}"
    with facts_path.open() as facts_fh:
        tmp_facts_path = facts_path.parent / (facts_path.name + ".tmp")
        with tmp_facts_path.open("w") as tmp:
            for line in facts_fh:
                line = re.sub(ts_re, ts_sub, line)
                line = re.sub(exp_re, exp_sub, line)
                tmp.write(line)
    # TODO: in python 3.7 theses move expects a str
    shutil.move(str(tmp_facts_path), str(facts_path))
