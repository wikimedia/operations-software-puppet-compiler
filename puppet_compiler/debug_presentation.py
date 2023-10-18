#!/usr/bin/env python3
"""Tool for debugging the human output of a compilation"""
import logging
import os
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path
from unittest.mock import DEFAULT, patch

from puppet_compiler.config import ControllerConfig
from puppet_compiler.directories import FHS, HostFiles
from puppet_compiler.prepare import ManageCode
from puppet_compiler.presentation import html
from puppet_compiler.state import ChangeState, StatesCollection


def get_args() -> Namespace:
    parser = ArgumentParser(description="Render dummy HTML output")
    parser.add_argument("-o", "--output", metavar="DIRECTORY", required=True, help="Directory to write output to")
    parser.add_argument("--force", action="store_true", help="Delete old directories before processing")
    return parser.parse_args()


def main() -> None:
    args = get_args()
    logging.basicConfig(level=logging.DEBUG)
    log = logging.getLogger(os.path.basename(__file__))

    CHANGE_ID = 1911
    JOB_ID = 42

    FHS.setup(
        change_id=CHANGE_ID,
        job_id=JOB_ID,
        base=args.output,
    )

    log.info("Preparing directories")
    os.makedirs(args.output, exist_ok=True)

    def mock_prepare_dir(directory):
        for x in ["src"]:
            os.makedirs(os.path.join(directory, x), exist_ok=True)

    code_manager = ManageCode(
        config=ControllerConfig(),
        jobid=JOB_ID,
        changeid=CHANGE_ID,
        force=args.force,
    )
    with patch.multiple(code_manager, _prepare_dir=DEFAULT, _fetch_change=DEFAULT) as mocks:
        mocks["_prepare_dir"].side_effect = mock_prepare_dir
        mocks["_fetch_change"].return_value = True
        try:
            code_manager.prepare()
        except FileExistsError as e:
            log.error(e)
            log.error("Use --force to have old directories cleaned up")
            sys.exit(e.errno)

    html.change_id = CHANGE_ID
    html.job_id = JOB_ID
    hosts_outputs = []
    hostnames = []
    state_cols = StatesCollection()

    for retcode, description in html.Host.retcode_descriptions.items():
        hostname = "%s001.example.org" % retcode
        hostnames.append(hostname)

        log.info("Generating %s (%s)" % (hostname, description))

        hostfiles = HostFiles(hostname=hostname)
        os.makedirs(hostfiles.outdir)

        hosts_outputs.append(hostfiles.outdir)

        state_cols.add(
            ChangeState(
                host=hostname,
                base_error=(retcode == "fail"),
                change_error=(retcode in ["fail", "error"]),
                has_diff=(retcode in ["core_diff", "diff"]) or None,
                has_core_diff=(retcode == "core_diff"),
                cancelled=(retcode == "cancelled"),
            )
        )

        html.Host(hostname=hostname, files=hostfiles, retcode=retcode).htmlpage()

    index = html.Index(outdir=FHS.output_dir, hosts_raw=",".join(hostnames))
    os.environ.update({"PUPPET_VERSION_FULL": "42.99"})

    index.render(state_cols)

    print("Rendered files:")
    hosts_outputs.sort()
    for output in [FHS.output_dir] + hosts_outputs:
        for html_file in Path(output).iterdir():
            if html_file.is_dir():
                continue
            print(html_file)


if __name__ == "__main__":
    main()
