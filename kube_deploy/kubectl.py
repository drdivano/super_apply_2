import json
import subprocess
from dotdict import DotDict

from kube_deploy.options import Options
from kube_deploy.log import DEBUG

class Result(bytes):
    def json(self):
        return json.loads(self.decode())

    def dict(self):
        return DotDict(self.json())


def kubectl(*args, input=None, dry_run=False, namespace=None):
    args = [str(v) for v in args]
    if namespace or Options.namespace:
        args = ['-n', (namespace or Options.namespace)] + args
    if dry_run:
        args.append('--dry-run')
    if input:
        DEBUG(input)
        input = convert_input(input)
    DEBUG(['kubectl'] + args)
    text = subprocess.check_output(['kubectl'] + args, input=input).strip()
    return Result(text)


def convert_input(input):
    if isinstance(input, str):
        input = input.encode()
    else:
        input = json.dumps(input).encode()
    return input
