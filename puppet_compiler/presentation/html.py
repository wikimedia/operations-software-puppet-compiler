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

    def _retcode_to_desc(self):
        if self.retcode == 'noop':
            return 'no change'
        elif self.retcode == 'diff':
            return 'changes detected'
        elif self.retcode == 'error':
            return 'change fails'
        else:
            return 'compiler failure'

    def htmlpage(self, diffs=None):
        """
        Create the html page
        """
        _log.debug("Rendering index page for %s", self.hostname)
        data = {'retcode': self.retcode, 'host': self.hostname}
        if self.retcode == 'diff' and diffs is not None:
            data['diffs'] = diffs
        data['desc'] = self._retcode_to_desc()
        t = env.get_template(self.tpl)
        page = t.render(jid=job_id, chid=change_id, **data)
        with open(os.path.join(self.outdir, self.page_name), 'w') as f:
            f.write(page)


class FutureHost(Host):
    tpl = 'hostpage.future.jinja2'
    page_name = 'index-future.html'

    def __init__(self, hostname, files, retcode):
        super(FutureHost, self).__init__(hostname, files, retcode)

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
        # page might contain non-ascii chars and generate UnicodeEncodeError
        # exceptions when trying to save its content to a file, so it is
        # explicitly encoded as utf-8 string.
        with open(self.outfile, 'w') as f:
            f.write(page.encode('utf-8'))


class FutureIndex(Index):
    tpl = 'index.future.jinja2'
    page_name = 'index-future.html'
