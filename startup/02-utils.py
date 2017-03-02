from __future__ import print_function
import os,sys
import numpy as np
from time import sleep

# xf16id - 5008, lix - 3009
def makedirs(path, mode=0o777, owner_uid=5008, group=3009):
    '''Recursively make directories and set permissions'''
    # Permissions not working with os.makedirs -
    # See: http://stackoverflow.com/questions/5231901
    if not path or os.path.exists(path):
        return []

    head, tail = os.path.split(path)
    ret = makedirs(head, mode)
    try:
        os.mkdir(path)
    except OSError as ex:
        if 'File exists' not in str(ex):
            raise

    os.chmod(path, mode)
    ret.append(path)
    return ret

def countdown(comment, duration):
    dt = duration
    while dt>0:
        print("%s %d s  \r"%(comment,dt), end="")
        dt -= 1
        sys.stdout.flush()
        sleep(1)
    print("done: %s %d s "%(comment,duration))