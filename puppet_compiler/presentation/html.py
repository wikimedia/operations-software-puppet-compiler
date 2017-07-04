import os
from jinja2 import Environment, PackageLoader
from puppet_compiler import _log

env = Environment(loader=PackageLoader('puppet_compiler', 'templates'))
change_id = None
job_id = None


class Host(object):

    def __init__(self, hostname, files, retcode):
        self.retcode = retcode
        self.hostname = hostname
        self.outdir = files.outdir
        self.diff_file = files.file_for('change', 'diff')

    def htmlpage(self):
        """
        Create the html page
        """
        _log.debug("Rendering index page for %s", self.hostname)
        data = {'retcode': self.retcode}
        if self.retcode == 'diff':
            with open(self.diff_file, 'r') as f:
                data['diffs'] = f.read()
        if self.retcode == 'noop':
            data['desc'] = 'no change'
        elif self.retcode == 'diff':
            data['desc'] = 'changes detected'
        elif self.retcode == 'err':
            data['desc'] = 'change fails'
        else:
            data['desc'] = 'compiler failure'
        t = env.get_template('hostpage.jinja2')
        page = t.render(host=self.hostname, jid=job_id, chid=change_id, **data)
        with open(os.path.join(self.outdir, 'index.html'), 'w') as f:
            f.write(page)


class Index(object):
    def __init__(self, outdir):
        self.outfile = os.path.join(outdir, 'index.html')

    def render(self, state):
        """
        Render the index page with info coming from state
        """
        _log.debug("Rendering the main index page")
        t = env.get_template('index.jinja2')
        page = t.render(state=state, jid=job_id, chid=change_id)
        with open(self.outfile, 'w') as f:
            f.write(page)
