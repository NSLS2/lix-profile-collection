print(f"Loading {__file__}...")

import os
import re
import shutil
import stat
import subprocess
import time

from IPython import get_ipython
from lixtools.sol.atsas import run as run_cmd

username = None
proposal_id = None
run_id = None
data_path = ""
collection_lock_file = f"{data_file_path.lustre_legacy.value}/.lock"
login_time = -1

def check_access(fn):
    if not os.path.exists(fn):
        raise Exception(f"{fn} does not exist ...")
    if os.access(fn, os.W_OK):
        print(f"write access to {fn} verified ...")
        return

    # this below may not be necessary
    out = run_cmd(["getfacl", "-cn", fn])
    wgrps = [int(t[:-4].lstrip("group:")) for t in re.findall("groups:[0-9]*:rw.", out)]
    ugrps = os.getgroups()
    if len(set(wgrps) & set(ugrps))==0:
        print("groups with write permission: ", wgrps)
        print("user group membership: ", ugrps)
        raise Exception(f"the current user does not have write access to {fn}")
    else:
        print(f"write access to {fn} verified ...")

def login(uname = None, pID = None, rID = None, debug=True, test_only=False):
    """ Ask the user for his credentials and proposal information for the data collection
        create_proc_dir: if True, create the directory where h5 files will be saved
        share_with: list of e-mails to share the proc_path with
    """
    #TODO: Use PASS and LDAP integration when possible.
    global username
    global proposal_id
    global run_id
    global data_path 
    global proc_path
    global login_time

    if 'owner' in RE.md.keys():
        logoff(quiet=True)

    correct_info = False
    if uname != None and pID!=None and rID!=None: 
        username = uname
        proposal_id = pID
        run_id = rID
        correct_info = True
    elif test_only:
        username = "lix"
        proposal_id = bl_comm_proposal
        if rID:
            run_id = rID
        else:
            run_id = "test"
        correct_info = True

    while not correct_info:
        username = input("Please enter your username: ")
        proposal_id = input("Please enter your proposal number: ")
        run_id = input("Please enter your run unique ID: ")

        print("You informed: \nUsername: {}\nProposal: {}\nRun ID:{}".format(username, proposal_id, run_id))
        correct_info = (input("Are the information above correct? [Y, N]: ") in ['Y', 'y'])

    RE.md['owner'] = username
    RE.md['proposal_id'] = proposal_id
    RE.md['data_session'] = f'pass-{proposal_id}'
    RE.md['run_id'] = run_id
    login_time = time.time()
    
    #rpath = f"{proposal_id}/{run_id}/"
    #data_path = f"{data_destination}/{rpath}"
    # makedirs(data_path, mode=0o0777) this will be created by the IOC?
    data_path = f"{data_destination}/%s/{current_cycle}/{proposal_id}/{run_id}/"
    RE.md['data_path'] = data_path   # different IOCs will be writing into subdirectories

    dgrp = f"{procdir_prefix}{proposal_id}"
    if test_only:
        proc_path = f"{proc_destination}/commissioning/{dgrp}/"
    else:
        proc_path = f"{proc_destination}/{current_cycle}/{dgrp}/"

    check_access(proc_path)
    proc_path += f"{run_id}/"
    RE.md['proc_path'] = proc_path
    if not os.path.isdir(proc_path):
        makedirs(proc_path, mode=0o2755)
        run_cmd(["setfacl", "-R", "-m", f"g:{dgrp}:rwX,d:g:{dgrp}:rwX", proc_path])
        makedirs(proc_path+"processed/")
        makedirs(proc_path+"img/")
  
    # if exp.h5 does not exist in proc_path, copy it from somewhere else
    # either the current directory, or from the proc_path of the last scan
    if not os.path.isfile(f"{proc_path}/exp.h5"):
        if os.path.isfile(f"{os.path.curdir}/exp.h5"):
            shutil.copy(f"{os.path.curdir}/exp.h5", f"{proc_path}")
        elif os.path.isfile(f"{db[-1].start['proc_path']}/exp.h5"):
            shutil.copy(f"{db[-1].start['proc_path']}/exp.h5", f"{proc_path}") 

    dw,mo,da,tt,yr = time.asctime().split()
    if not os.path.isdir(proc_path+"log"):
        os.mkdir(proc_path+"log")
    logfile = proc_path+("log/%s." % username)+yr+mo+("%02d_" % int(da))+tt.replace(':', '')
    ip = get_ipython()
    ip.run_line_magic("logstop", "")
    ip.run_line_magic("logstart", f"-ort {logfile}")
    ip.logger.log_write(f"**LOGIN** {username} @ {time.asctime()}\n")    

    if debug:
        def print_time_callback(name, doc):
            if name =='start':
                t1 = time.time()
                print("#STARTDOC : {}".format(t1))
                print("#STARTDOC : {}".format(time.ctime(t1)))
        RE.subscribe(print_time_callback)

def get_IOC_datapath(ioc_name, substitute_path=None):
    if data_path=="":
        print("login first to specify data path:")
        login()
    if substitute_path:
        return data_path.replace(data_destination, substitute_path)%ioc_name
    else:
        return data_path%ioc_name
        
def write_log_msg(msg):
    ip = get_ipython()
    ip.logger.log_write(msg)


def touch(fname):
    try:
        os.utime(fname, None)
    except OSError:
        open(fname, 'a').close()
    
def write_lock(num):
    lkf = open(collection_lock_file, "w")
    lkf.write("%d" % num)
    lkf.close()
    
def read_lock():
    lkf = open(collection_lock_file, "r")
    ret = lkf.read()
    lkf.close()
    return int(ret)
    
def get_lock():
    
    if os.path.exists(collection_lock_file):
        ret = read_lock()
        if ret !=0 and ret!=os.getpid():
            raise RuntimeError("data collection lock exist. you can\'t collect while others are collecting")
    else:
        touch(collection_lock_file)
        os.chmod(collection_lock_file, 0o777)
    
    write_lock(os.getpid())
    
def release_lock():
    if os.path.exists(collection_lock_file):
        ret = read_lock()
        if ret !=0 and ret!=os.getpid():
            raise RuntimeError("data collection lock exist. you can\'t release a lock created by others")

    write_lock(0)
            
def change_path():
    global data_path 
    global collection_lock_file
    
    if username==None or proposal_id==None or run_id==None:
        login()

    
def logoff(quiet=False):
    global username
    global proposal_id
    global run_id
    global data_path 
    global proc_path
    global login_time
    
    """Clear the login information"""
    if not quiet: 
        if (input("Are you sure you want to logout? [Y, N]: ") not in ['Y', 'y']):
            return

    if 'owner' in RE.md.keys():
        msg = f"**LOGOFF** {RE.md['owner']}\n"
        if login_time>0:
            dt = time.time()-login_time
            msg += f" , time logged in = {dt/3600:.2f} hours\n"
        write_log_msg(msg)

    username = None
    proposal_id = None
    run_id = None
    data_path = ""
    proc_path = None

    for k in ['owner', 'proposal_id', 'run_id', 'data_path', 'proc_path']:
        if k in RE.md.keys():
            del RE.md[k]

    ip = get_ipython()
    ip.run_line_magic("logstop", "")
 
