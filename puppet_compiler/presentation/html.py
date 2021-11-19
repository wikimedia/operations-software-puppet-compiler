"""Html templating module"""
import os
from pathlib import Path
from typing import Any, Dict, Optional, Set

from jinja2 import Environment, PackageLoader

from puppet_compiler import _log
from puppet_compiler.directories import HostFiles
from puppet_compiler.state import StatesCollection

env = Environment(loader=PackageLoader("puppet_compiler", "templates"))
change_id: Optional[int] = None
job_id: Optional[int] = None


# pylint: disable=too-few-public-methods
class Host:
    """Template for a host"""

    tpl: str = "hostpage.jinja2"
    page_name: str = "index.html"
    mode: str = "prod"
    pretty_mode: str = "Production"
    retcode_descriptions: Dict[str, str] = {"noop": "no change", "diff": "changes detected", "error": "change fails"}

    def __init__(self, hostname: str, files: HostFiles, retcode: str):
        self.retcode = retcode
        self.hostname = hostname
        self.outdir = files.outdir

    def _retcode_to_desc(self) -> str:
        return self.retcode_descriptions.get(self.retcode, "compiler failure")

    def _renderpage(self, page_name: str, diffs: Optional[Dict] = None) -> None:
        _log.debug("Rendering %s for %s", page_name, self.hostname)
        data: Dict[Any, Any] = {"retcode": self.retcode, "host": self.hostname}
        if self.retcode == "diff" and diffs is not None:
            data["diffs"] = diffs
        data["desc"] = self._retcode_to_desc()
        data["mode"] = self.mode
        data["pretty_mode"] = self.pretty_mode
        data["hosts_raw"] = self.hostname
        data["page_name"] = page_name
        tpl = env.get_template(self.tpl)
        page = tpl.render(jid=job_id, chid=change_id, **data)
        file_path = self.outdir / page_name
        file_path.write_text(page)

    def htmlpage(self, diffs: Optional[Dict] = None, full_diffs: Optional[Dict] = None) -> None:
        """
        Create the html page
        """
        self._renderpage("fulldiff.html", full_diffs)
        self._renderpage(self.page_name, diffs)


class Index:
    """Class for rendering index page"""

    tpl: str = "index.jinja2"
    page_name: str = "index.html"
    messages: Dict[str, str] = {
        "change": "when the change is applied",
        "fail": "have failed to compile completely",
    }

    def __init__(self, outdir: Path, hosts_raw: str) -> None:
        if self.page_name == "index.html":
            self.url = ""
        else:
            self.url = self.page_name
        self.outfile = outdir / self.page_name
        self.hosts_raw = hosts_raw

    def render(self, states_col: StatesCollection, partial: bool = False) -> None:
        """
        Render the index page with info coming from state
        """
        ok_hosts: Set[str] = states_col.states.get("noop", set())
        fail_hosts: Set[str] = states_col.states.get("fail", set())
        cancelled_hosts: Set[str] = set() if partial else states_col.states.get("cancelled", set())
        unfinished_hosts: Set[str] = states_col.states.get("cancelled", set()) if partial else set()

        _log.debug("Rendering the main index page")
        tpl = env.get_template(self.tpl)
        page = tpl.render(
            ok_hosts=ok_hosts,
            fail_hosts=fail_hosts,
            cancelled_hosts=cancelled_hosts,
            unfinished_hosts=unfinished_hosts,
            msg=self.messages,
            state=states_col.states,
            jid=job_id,
            chid=change_id,
            page_name=self.page_name,
            hosts_raw=self.hosts_raw,
            puppet_version=os.environ["PUPPET_VERSION_FULL"],
        )
        with open(self.outfile, "w") as outfile:
            outfile.write(page)
