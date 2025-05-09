import os
import re
import subprocess
from collections import namedtuple

def parse_api_resources(text):
    header = None
    for line in text.split('\n'):
        line = line.rstrip('\r\n')
        if not line:
            continue
        if header is None:
            matches = re.findall(r'\S+\s*', line)
            header = []
            start = 0
            for part in matches:
                label = part.rstrip()
                end = start + len(part)
                header.append((label, start, end))
                start = end
        else:
            fields = {}
            for label, start, end in header:
                fields[label] = line[start:end].rstrip()
            yield fields


ResourceInfo = namedtuple('ResourceInfo', ['name', 'kind', 'shortnames', 'apigroup', 'namespaced'])

def load_api_resources(parsed_table):
    kinds = {}
    for record in parsed_table:
        ri = ResourceInfo(record['NAME'], record['KIND'], record['SHORTNAMES'].split(','), record['APIGROUP'],
                          record['NAMESPACED'] == 'true')
        kinds[ri.kind] = ri
        kinds[ri.kind.lower()] = ri
    return kinds


def refresh_api_resources():
    text = subprocess.check_output(['kubectl', 'api-resources', '-o', 'wide'])
    global KINDS
    KINDS.clear()
    KINDS.update(load_api_resources(parse_api_resources(text.decode())))


MODULE_DIR = os.path.dirname(os.path.realpath(__file__))

# load kubernetes standard api resources
# kubectl api-resources -o wide > default_api_resources.txt
with open(MODULE_DIR + '/standard_api_resources.txt') as f:
    KINDS = load_api_resources(parse_api_resources(f.read()))

