from __future__ import print_function
import os,sys
import numpy as np
from time import sleep
from datetime import datetime

# xf16id - 5008, lix - 3009
def makedirs(path, mode=None, owner_uid=5008, group=3009):
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

    if mode is not None:
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

# this should be used for RE.msg_hook only    
def print_time(msg):
    now = datetime.now()
    if not hasattr(print_time, "waiting"):
        print_time.previous_time = 0
        print_time.waiting = False
    else:
        if print_time.waiting == True:
            print("%.3f sec lapsed since last wait msg." % (time.time()-print_time.previous_time))
        if msg[:4]=="wait":
            print_time.waiting = True
            print_time.previous_time = time.time()
        else:
            print_time.waiting = False
            print(now.strftime("%H:%M:%S.%f")[:-3], msg)


def setPV(pv_name, value, readback_pv_name=None, poll_time=0.25, time_out=5, retry=5):
    """ It has been observed that sometimes EPICS PVs set value somehow gets lost when 
        using caput(). This function attempts to correct this problem by trying for 
        multiple times until the value has changed.
    """
    if readback_pv_name is None:
        readback_pv_name = pv_name
    for i in range(retry):
        caput(pv_name, value)
        for t in range(int(time_out/poll_time)):
            ret = caget(readback_pv_name)
            if ret==value:
                return
            time.sleep(poll_time)
        print(f"failed to set {pv_name} to {value}, retry # {i+1}")
    raise Exception(f'setPV(), giving up after {retry} tries.')

def setSignal(signal, value, readback_signal=None, poll_time=0.25, time_out=5, retry=5):
    if readback_signal is None:
        readback_signal = signal
    for i in range(retry):
        signal.put(value)
        for t in range(int(time_out/poll_time)):
            ret = readback_signal.get()
            if ret==value:
                return
            time.sleep(poll_time)
        print(f"failed to set {signal} to {value}, retry # {i+1}")
    raise Exception(f'setSignal(), giving up after {retry} tries.')
    
    
