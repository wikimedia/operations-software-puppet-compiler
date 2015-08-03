import os
import re
import subprocess
from tempfile import SpooledTemporaryFile as spoolfile
from puppet_compiler import _log


def compile(hostname, basedir, vardir):
    """
    Compile the catalog
    """
    env = os.environ.copy()
    srcdir = os.path.join(basedir, 'src')
    privdir = os.path.join(basedir, 'private')
    env['RUBYLIB'] = os.path.join(srcdir, 'modules/wmflib/lib/')

    catalogdir = os.path.join(basedir, 'catalogs')
    tpldir = os.path.join(srcdir, 'templates')
    cmd = ['puppet', 'master',
           '--vardir=%s' % vardir,
           '--modulepath=%s:%s' % (os.path.join(privdir, 'modules'),
                                   os.path.join(srcdir, 'modules')),
           '--confdir=%s' % srcdir,
           '--templatedir=%s' % tpldir,
           '--compile=%s' % hostname,
           '--color=false'
    ]
    hostfile = os.path.join(catalogdir, hostname)

    with open(hostfile + ".err", 'w') as err:
        out = spoolfile()
        subprocess.check_call(cmd, stdout=out, stderr=err, env=env)

    # Puppet outputs a lot of garbage to stdout...
    with open(hostfile + ".pson", "w") as f:
        out.seek(0)
        for line in out:
            if not re.match('(Info|[Nn]otice|[Ww]arning)', line):
                f.write(line)


def diff(basedir, hostname):
    """
    Compute the diffs between the two changes
    """
    prod_catalog = os.path.join(basedir,
                                'production',
                                'catalogs',
                                hostname + '.pson')
    change_catalog = os.path.join(basedir,
                                  'change',
                                  'catalogs',
                                  hostname + '.pson')
    output = os.path.join(basedir, 'diffs', hostname + '.diff')
    cmd = [ 'puppet', 'catalog', 'diff', '--show_resource_diff',
            '--content_diff', prod_catalog, change_catalog]
    temp = spoolfile()
    subprocess.check_call(cmd, stdout=temp)
    with open(output, 'w') as out:
        temp.seek(0)
        # Remove bold from term output
        out.write(temp.read().replace('\x1b[1m', '').replace('\x1b[0m', ''))
