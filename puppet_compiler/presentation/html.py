import os
from jinja2 import Environment, PackageLoader
from puppet_compiler import _log

env = Environment(loader=PackageLoader('puppet_compiler', 'templates'))
change_id = None
job_id = None


class Host(object):
    tpl = 'hostpage.jinja2'
    page_name = 'index.html'

    def __init__(self, hostname, files, retcode):
        self.retcode = retcode
        self.hostname = hostname
        self.outdir = files.outdir
        self.diff_file = files.file_for('change', 'diff')

    def _retcode_to_desc(self):
        if self.retcode == 'noop':
            return 'no change'
        elif self.retcode == 'diff':
            return 'changes detected'
        elif self.retcode == 'error':
            return 'change fails'
        else:
            return 'compiler failure'

    def htmlpage(self):
        """
        Create the html page
        """
        _log.debug("Rendering index page for %s", self.hostname)
        data = {'retcode': self.retcode}
        if self.retcode == 'diff':
            with open(self.diff_file, 'r') as f:
                data['diffs'] = f.read()
        data['desc'] = self._retcode_to_desc()
        t = env.get_template(self.tpl)
        page = t.render(host=self.hostname, jid=job_id, chid=change_id, **data)
        with open(os.path.join(self.outdir, self.page_name), 'w') as f:
            f.write(page)


class FutureHost(Host):
    tpl = 'hostpage.future.jinja2'
    page_name = 'index-future.html'

    def __init__(self, hostname, files, retcode):
        super(FutureHost, self).__init__(hostname, files, retcode)
        self.diff_file = files.file_for('future', 'diff')

    def _retcode_to_desc(self):
        if self.retcode == 'break':
            return 'change breaks the current parser'
        elif self.retcode == 'error':
            return 'change is not compatible with the future parser'
        elif self.retcode == 'ok':
            return 'change works with both parsers'
        elif self.retcode == 'diff':
            return 'change works with both parsers, with diffs'


class Index(object):
    tpl = 'index.jinja2'
    page_name = 'index.html'

    def __init__(self, outdir):
        if self.page_name == 'index.html':
            self.url = ""
        else:
            self.url = self.page_name
        self.outfile = os.path.join(outdir, self.page_name)

    def render(self, state):
        """
        Render the index page with info coming from state
        """
        _log.debug("Rendering the main index page")
        t = env.get_template(self.tpl)
        # TODO: support multiple modes
        page = t.render(state=state, jid=job_id, chid=change_id)
        with open(self.outfile, 'w') as f:
            f.write(page)


class FutureIndex(Index):
    tpl = 'index.future.jinja2'
    page_name = 'index-future.html'
