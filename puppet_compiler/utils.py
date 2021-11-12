"""Collections of helpers"""
import re
import shutil
from datetime import datetime, timedelta

from puppet_compiler import _log


class FactsFileNotFound(Exception):
    """Exception for missing facts files"""


def facts_file(vardir, hostname):
    """Finds facts file for the given hostname.  Search subdirs recursively.
    If we find multiple matches, return the newest one."""
    try:
        # try to get the most recent fact file based on the file mtime
        return sorted(
            (vardir / "yaml").glob(f"**/facts/{hostname}.yaml"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )[0]
    except IndexError as error:
        raise FactsFileNotFound(f"Unable to find fact file for: {hostname} under directory {vardir}") from error


def refresh_yaml_date(facts_file):
    """
    Refresh the timestamp and the expiration of the yaml facts cache
    to avoid incurring in https://tickets.puppetlabs.com/browse/PUP-5441
    when using puppetdb.
    """
    # No, we cannot read the yaml. It contains ruby data structures.
    date_format = "%Y-%m-%d %H:%M:%S.%s +00:00"
    _log.debug("Patching %s", facts_file)
    ts_re = r"(\s+\"_timestamp\":) .*"
    exp_re = r"(\s+expiration:) .*"
    datetime_facts = datetime.utcnow()
    datetime_exp = datetime_facts + timedelta(days=1)
    ts_sub = f"\\1 {datetime_facts.strftime(date_format)}"
    exp_sub = f"\\1 {datetime_exp.strftime(date_format)}"
    with facts_file.open() as facts_fh:
        tmp_facts_file = facts_file.parent / (facts_file.name + ".tmp")
        with tmp_facts_file.open("w") as tmp:
            for line in facts_fh:
                line = re.sub(ts_re, ts_sub, line)
                line = re.sub(exp_re, exp_sub, line)
                tmp.write(line)
    shutil.move(tmp_facts_file, facts_file)
