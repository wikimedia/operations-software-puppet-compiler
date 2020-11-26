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


class FutureHost(Host):
    page_name = 'index-future.html'
    mode = 'future'
    pretty_mode = 'Future parser'
    retcode_descriptions = {
        'break': 'change breaks the current parser',
        'ok': 'change works with both parsers',
        'diff': 'change works with both parsers, with diffs'
    }

    def __init__(self, hostname, files, retcode):
        super(FutureHost, self).__init__(hostname, files, retcode)
        self.retcode_descriptions['error'] = 'change is not compatible with the {}'.format(
            self.pretty_mode)


class RichDataHost(FutureHost):
    mode = 'rich_data'
    pretty_mode = 'RichData'
    page_name = 'index-rich_data.html'


class Index(object):
    tpl = 'index.jinja2'
    page_name = 'index.html'
    mode = 'standard'
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
        if self.mode == 'standard':
            ok_hosts = state.get('noop', [])
            fail_hosts = state.get('fail', [])
        else:
            ok_hosts = state.get('ok', [])
            fail_hosts = state.get('break', [])

        _log.debug("Rendering the main index page")
        tpl = env.get_template(self.tpl)
        page = tpl.render(ok_hosts=ok_hosts, fail_hosts=fail_hosts, msg=self.messages,
                          state=state, jid=job_id, chid=change_id, page_name=self.page_name,
                          mode=self.mode, hosts_raw=self.hosts_raw,
                          puppet_version=os.environ['PUPPET_VERSION_FULL'])
        with open(self.outfile, 'w') as outfile:
            outfile.write(page)


class FutureIndex(Index):
    page_name = 'index-future.html'
    mode = 'future'

    def __init__(self, outdir, hosts_raw):
        super(FutureIndex, self).__init__(outdir, hosts_raw)
        self.messages = {
            'change': 'with the {} parser'.format(self.mode),
            'fail': 'break with the current parser',
        }


class RichDataIndex(FutureIndex):
    page_name = 'index-rich_data.html'
    mode = 'rich_data'
