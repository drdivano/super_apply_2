import argparse

class Options(argparse.Namespace):
    parser = argparse.ArgumentParser()
    debug = 0
    verbose = False
    quiet = False
    namespace = None
    dry_run = None
    overwrite = None
    force_version = None
    no_version = None

