import os
import re
import subprocess

from tempfile import SpooledTemporaryFile as spoolfile

from puppet_compiler import _log
from puppet_compiler.directories import HostFiles, FHS
from puppet_compiler import utils


def compile_cmd_env(hostname, label, vardir, *extra_flags):
    puppet_version = int(os.environ.get('PUPPET_VERSION', 4))
    env = os.environ.copy()
    if label == 'prod':
        basedir = FHS.prod_dir
    else:
        basedir = FHS.change_dir

    srcdir = os.path.join(basedir, 'src')
    privdir = os.path.join(basedir, 'private')
    env['RUBYLIB'] = os.path.join(srcdir, 'modules/wmflib/lib/')

    # factsfile will be something like
    #  "/foo/yaml/facts/production/facts/hostname.yaml
    # puppet will look for a subdir named 'facts' for
    # the yaml files, so we need to prune this path
    # accordingly.
    #
    # We can safely assume that factsfile is a valid path
    # since we would have errored out earlier if it's
    # unknown.
    factsfile = utils.facts_file(vardir, hostname)
    yamldir = os.path.dirname(os.path.dirname(factsfile))

    cmd = ['puppet', 'master',
           '--vardir=%s' % vardir,
           '--modulepath=%s:%s' % (os.path.join(privdir, 'modules'),
                                   os.path.join(srcdir, 'modules')),
           '--confdir=%s' % srcdir,
           '--compile=%s' % hostname,
           '--color=false',
           '--yamldir=%s' % yamldir,
           '--manifest=$confdir/manifests',
           '--environmentpath=$confdir/environments'
           ]
    if puppet_version < 4:
        cmd.extend(['--trusted_node_data', '--parser=future', '--environment=future'])
    cmd.extend(extra_flags)
    return (cmd, env)


def compile(hostname, label, vardir, *extra_flags):
    """
    Compile the catalog
    """
    cmd, env = compile_cmd_env(hostname, label, vardir, *extra_flags)
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


def compile_storeconfigs(hostname, vardir):
    """
    Specialized function to store data into puppetdb
    when compiling.
    """
    cmd, env = compile_cmd_env(hostname, 'prod', vardir, '--storeconfigs', '--storeconfigs_backend=puppetdb')
    out = spoolfile()
    err = spoolfile()
    success = False

    try:
        subprocess.check_call(cmd, stdout=out, stderr=err, env=env)
        success = True
    except subprocess.CalledProcessError as e:
        _log.exception("Compilation failed for host %s: %s", hostname, e)

    out.seek(0)
    err.seek(0)
    return (success, out, err)
