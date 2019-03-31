import re
import os
import shutil

from datetime import datetime, timedelta
from puppet_compiler import _log


def facts_file(vardir, hostname):
    """Finds facts file for the given hostname.  Search subdirs recursively.
       If we find multiple matches, return the newest one."""
    filename = '{}.yaml'.format(hostname)
    latestfile = ""
    mtime = 0
    for dirpath, dirnames, files in os.walk(os.path.join(vardir, 'yaml')):
        # Puppet can only see things in directories named 'facts'
        if os.path.basename(os.path.normpath(dirpath)) == 'facts' and filename in files:
            filepath = os.path.join(dirpath, filename)
            if os.path.getmtime(filepath) > mtime:
                latestfile = filepath
                mtime = os.path.getmtime(filepath)
    return latestfile


def refresh_yaml_date(facts_file):
    """
    Refresh the timestamp and the expiration of the yaml facts cache
    to avoid incurring in https://tickets.puppetlabs.com/browse/PUP-5441
    when using puppetdb.
    """
    # No, we cannot read the yaml. It contains ruby data structures.
    date_format = '%Y-%m-%d %H:%M:%S.%s +00:00'
    _log.debug("Patching {}".format(facts_file))
    ts_re = r'(\s+\"_timestamp\":) .*'
    exp_re = r'(\s+expiration:) .*'
    datetime_facts = datetime.utcnow()
    datetime_exp = (datetime_facts + timedelta(days=1))
    ts_sub = r'\1 {}'.format(datetime_facts.strftime(date_format))
    exp_sub = r'\1 {}'.format(datetime_exp.strftime(date_format))
    with open(facts_file, 'r') as fh:
        with open(facts_file + '.tmp', 'w') as tmp:
            for line in fh:
                line = re.sub(ts_re, ts_sub, line)
                line = re.sub(exp_re, exp_sub, line)
                tmp.write(line)
    shutil.move(facts_file + '.tmp', facts_file)
