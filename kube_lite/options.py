import argparse

class Options(argparse.Namespace):
    debug = 0
    verbose = False
    quiet = False
    namespace = None
    dry_run = None
    wait = 300
