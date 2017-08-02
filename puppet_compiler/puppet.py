import os
import re
import subprocess
from tempfile import SpooledTemporaryFile as spoolfile
from directories import HostFiles, FHS


def compile(hostname, label, vardir, *extra_flags):
    """
    Compile the catalog
    """
    env = os.environ.copy()
    if label == 'prod':
        basedir = FHS.prod_dir
    else:
        basedir = FHS.change_dir

    srcdir = os.path.join(basedir, 'src')
    privdir = os.path.join(basedir, 'private')
    env['RUBYLIB'] = os.path.join(srcdir, 'modules/wmflib/lib/')

    tpldir = os.path.join(srcdir, 'templates')
    cmd = ['puppet', 'master',
           '--vardir=%s' % vardir,
           '--modulepath=%s:%s' % (os.path.join(privdir, 'modules'),
                                   os.path.join(srcdir, 'modules')),
           '--confdir=%s' % srcdir,
           '--templatedir=%s' % tpldir,
           '--trusted_node_data',
           '--compile=%s' % hostname,
           '--color=false'
           ]
    cmd.extend(extra_flags)
    hostfiles = HostFiles(hostname)

    with open(hostfiles.file_for(label, 'errors'), 'w') as err:
        out = spoolfile()
        subprocess.check_call(cmd, stdout=out, stderr=err, env=env)

    # Puppet outputs a lot of garbage to stdout...
    with open(hostfiles.file_for(label, 'catalog'), "w") as f:
        out.seek(0)
        for line in out:
            if not re.match('(Info|[Nn]otice|[Ww]arning)', line):
                f.write(line)
