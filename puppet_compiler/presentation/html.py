import os

from jinja2 import Environment, PackageLoader
from puppet_compiler import _log

env = Environment(loader=PackageLoader('puppet_compiler', 'templates'))
change_id = None
job_id = None


class Host(object):
    tpl = 'hostpage.jinja2'
    page_name = 'index.html'
    mode = 'prod'
    pretty_mode = 'Production'
    retcode_descriptions = {
        'noop': 'no change',
        'diff': 'changes detected',
        'error': 'change fails'
    }

    def __init__(self, hostname, files, retcode):
        self.retcode = retcode
        self.hostname = hostname
        self.outdir = files.outdir

    def _retcode_to_desc(self):
        return self.retcode_descriptions.get(self.retcode, 'compiler failure')

    def _renderpage(self, page_name, diffs=None):
        _log.debug("Rendering %s for %s", page_name, self.hostname)
        data = {'retcode': self.retcode, 'host': self.hostname}
        if self.retcode == 'diff' and diffs is not None:
            data['diffs'] = diffs
        data['desc'] = self._retcode_to_desc()
        data['mode'] = self.mode
        data['pretty_mode'] = self.pretty_mode
        data['hosts_raw'] = self.hostname
        data['page_name'] = page_name
        tpl = env.get_template(self.tpl)
        page = tpl.render(jid=job_id, chid=change_id, **data)
        file_path = os.path.join(self.outdir, page_name)
        with open(file_path, 'w') as outfile:
            outfile.write(page)

    def htmlpage(self, diffs=None, full_diffs=None):
        """
        Create the html page
        """
        self._renderpage('fulldiff.html', full_diffs)
        self._renderpage(self.page_name, diffs)


class Index(object):
    tpl = 'index.jinja2'
    page_name = 'index.html'
    messages = {
        'change': 'when the change is applied',
        'fail': 'have failed to compile completely',
    }

    def __init__(self, outdir, hosts_raw):
        if self.page_name == 'index.html':
            self.url = ""
        else:
            self.url = self.page_name
        self.outfile = os.path.join(outdir, self.page_name)
        self.hosts_raw = hosts_raw

    def render(self, state):
        """
        Render the index page with info coming from state
        """
        ok_hosts = state.get('noop', [])
        fail_hosts = state.get('fail', [])

        _log.debug("Rendering the main index page")
        tpl = env.get_template(self.tpl)
        page = tpl.render(ok_hosts=ok_hosts, fail_hosts=fail_hosts, msg=self.messages,
                          state=state, jid=job_id, chid=change_id, page_name=self.page_name,
                          hosts_raw=self.hosts_raw,
                          puppet_version=os.environ['PUPPET_VERSION_FULL'])
        with open(self.outfile, 'w') as outfile:
            outfile.write(page)
