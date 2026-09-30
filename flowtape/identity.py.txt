"""Stable persisted node identities; presentation numbers are independent."""

import time
import uuid

CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'


def ulid():
    number = (int(time.time()*1000)<<80) | (uuid.uuid4().int & ((1<<80)-1))
    return ''.join(CROCKFORD[(number>>(5*shift))&31] for shift in range(25,-1,-1))


def ensure_ids(document):
    from .editor import walk_nodes
    for node in walk_nodes(document['steps']):
        node.setdefault('_meta', {'id':ulid()})
