import os


class FHS(object):
    base_dir = None
    prod_dir = None
    change_dir = None
    diff_dir = None
    output_dir = None

    @classmethod
    def setup(cls, job_id, base):
        cls.base_dir = os.path.join(base, str(job_id))
        cls.prod_dir = os.path.join(cls.base_dir, 'production')
        cls.change_dir = os.path.join(cls.base_dir, 'change')
        cls.diff_dir = os.path.join(cls.base_dir, 'diffs')
        cls.output_dir = os.path.join(base, 'output', str(job_id))


class HostFiles(object):

    def __init__(self, hostname):
        self.hostname = hostname
        self.outdir = os.path.join(FHS.output_dir, self.hostname)

    def file_for(self, env, what):
        if env in ['prod', 'change']:
            suffix = ""
        else:
            suffix = "-%s" % env

        if what == 'diff':
            return os.path.join(FHS.diff_dir, self.hostname + suffix + '.diff')

        if env == 'prod':
            base = FHS.prod_dir
        else:
            base = FHS.change_dir

        if what == 'catalog':
            ext = '.pson'
        elif what == 'errors':
            ext = '.err'
        else:
            raise ValueError('Unrecognized object: %s' % what)
        return os.path.join(base, 'catalogs', self.hostname + suffix + ext)

    def outfile_for(self, env, what):
        name = os.path.basename(self.file_for(env, what))
        return os.path.join(self.outdir, env + '.' + name)
