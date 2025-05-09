# -*- coding: utf-8 -*-
import logging
import sys
from kube_deploy.options import Options

CONSOLE_FILE = sys.stderr
DEBUG_FILE = sys.stderr
ERROR_FILE = sys.stderr

def setup_logging(console_file=None, debug_file=None,):
    logger = logging.getLogger()
    if Options.debug >= 2:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler())
    if console_file:
        global CONSOLE_FILE
        CONSOLE_FILE = console_file
    if debug_file:
        global DEBUG_FILE
        DEBUG_FILE = debug_file

def CONSOLE(*args):
    if not Options.quiet:
        print(' '.join(str(s) for s in args), file=CONSOLE_FILE, flush=True)

def ERROR(*args):
    print(' '.join(str(s) for s in args), file=ERROR_FILE, flush=True)

def DEBUG(*args, level=1):
    if Options.debug < level:
        return
    parts = []
    for arg in args:
        if hasattr(arg, '__call__'):
            arg = arg()
        parts.append(str(arg))
    print(' '.join(parts), file=DEBUG_FILE, flush=True)

def indent_multiline(msg, prepend='#     '):
    parts = []
    for line in msg.split('\n'):
        parts.append(prepend + line)
    return '\n'.join(parts)

def print_container_log(log, pod_name, container_name):
    CONSOLE('# ---------- %s/%s' % (pod_name, container_name))
    CONSOLE(indent_multiline(log.rstrip()))
    CONSOLE('# ---------- end')
