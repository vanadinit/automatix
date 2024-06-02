import os
import pickle
import subprocess
import sys
from argparse import Namespace
from copy import deepcopy
from csv import DictReader
from importlib import import_module
from tempfile import TemporaryDirectory
from time import time
from typing import List

from .automatix import Automatix
from .command import Command, SkipBatchItemException, AbortException
from .config import arguments, CONFIG, get_script, LOG, update_script_from_row, collect_vars, SCRIPT_FIELDS, VERSION
from .parallel import run_from_pipe

try:
    import python_progress_bar as progress_bar

    PROGRESS_BAR = True
except ImportError:
    PROGRESS_BAR = False


def setup(args: Namespace):
    """Setup logger and print version information"""
    if CONFIG.get('logging_lib'):
        log_lib = import_module(CONFIG.get('logging_lib'))
        init_logger = log_lib.init_logger
    else:
        from .logger import init_logger

    init_logger(name=CONFIG['logger'], debug=args.debug)

    LOG.info(f'Automatix Version {VERSION}')

    configfile = CONFIG.get('config_file')
    if configfile:
        LOG.info(f'Using configuration from: {configfile}')
    else:
        LOG.warning('Configuration file not found or not configured. Using defaults.')


def get_command_class() -> type:
    if CONFIG.get('bundlewrap'):
        from .bundlewrap import BWCommand, AutomatixBwRepo

        CONFIG['bw_repo'] = AutomatixBwRepo(repo_path=os.environ.get('BW_REPO_PATH', '.'))
        return BWCommand
    else:
        return Command


def get_script_and_batch_items(args: Namespace) -> (dict, list):
    script = get_script(args=args)

    batch_items: List[dict] = [{}]
    if args.vars_file:
        with open(args.vars_file) as csvfile:
            batch_items = list(DictReader(csvfile))
        script['batch_mode'] = False if args.parallel else True
        script['batch_items_count'] = 1 if args.parallel else len(batch_items)
        LOG.notice(f'Detected {"parallel" if args.parallel else "batch"} processing from CSV file.')

    if args.steps:
        exclude = script['exclude'] = args.steps.startswith('e')
        script['steps'] = {int(s) for s in (args.steps[1:] if exclude else args.steps).split(',')}

    return script, batch_items


def run_batch_items(script: dict, batch_items: list, args: Namespace):
    cmd_class = get_command_class()

    for i, row in enumerate(batch_items, start=1):
        script_copy = deepcopy(script)
        update_script_from_row(row=row, script=script_copy, index=i)

        variables = collect_vars(script_copy)

        auto = Automatix(
            script=script_copy,
            variables=variables,
            config=CONFIG,
            cmd_class=cmd_class,
            script_fields=SCRIPT_FIELDS,
            cmd_args=args,
            batch_index=i,
        )
        auto.env.attach_logger()
        auto.set_command_count()
        try:
            auto.run()
        except SkipBatchItemException as exc:
            LOG.info(str(exc))
            LOG.notice('=====> Jumping to next batch item.')
            continue
        except AbortException as exc:
            sys.exit(int(exc))
        except KeyboardInterrupt:
            LOG.warning('\nAborted by user. Exiting.')
            sys.exit(130)


def run_parallel_screens(script: dict, batch_items: list, args: Namespace):
    progress_bar.destroy_scroll_area()
    LOG.info('Preparing automatix objects for parallel processing')

    cmd_class = get_command_class()
    with TemporaryDirectory() as tempdir:
        LOG.info(f'Using temporary directory to save object files: {tempdir}')
        for i, row in enumerate(batch_items, start=1):
            script_copy = deepcopy(script)
            update_script_from_row(row=row, script=script_copy, index=i)

            variables = collect_vars(script_copy)

            auto = Automatix(
                script=script_copy,
                variables=variables,
                config=CONFIG,
                cmd_class=cmd_class,
                script_fields=SCRIPT_FIELDS,
                cmd_args=args,
                batch_index=1,
            )
            auto.set_command_count()
            with open(f'{tempdir}/auto{i}', 'wb') as f:
                pickle.dump(obj=auto, file=f)

        time_id = round(time())
        os.mkfifo(f'{tempdir}/{time_id}_finished')
        subprocess.run(
            f'screen -S {time_id}_overview automatix nonexistent --prepared-from-pipe "{tempdir}/{time_id}_overview"',
            shell=True,
        )
        with open(f'{tempdir}/{time_id}_finished') as fifo:
            LOG.info('Wait for overview to finish')
            for _ in fifo:
                LOG.info('Automatix finished parallel processing')
    LOG.info('Temporary directory cleaned up')


def main():
    if os.getenv('AUTOMATIX_SHELL'):
        print('You are running Automatix from an interactive shell of an already running Automatix!')
        answer = input('Do you really want to proceed? Then type "yes" and ENTER.\n')
        if answer != 'yes':
            sys.exit(0)

    starttime = time()
    args = arguments()
    setup(args=args)

    try:
        if PROGRESS_BAR:
            progress_bar.setup_scroll_area()
        if pipe := args.prepared_from_pipe:
            run_from_pipe(pipe=pipe)
            sys.exit(0)

        script, batch_items = get_script_and_batch_items(args=args)

        if args.vars_file and args.parallel:
            run_parallel_screens(script=script, batch_items=batch_items, args=args)
        else:
            run_batch_items(script=script, batch_items=batch_items, args=args)
    finally:
        if PROGRESS_BAR:
            progress_bar.destroy_scroll_area()

    if 'AUTOMATIX_TIME' in os.environ:
        LOG.info(f'The Automatix script took {round(time() - starttime)}s!')
