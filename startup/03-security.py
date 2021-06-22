import os,stat,time,shutil
from IPython import get_ipython

username = None
proposal_id = None
run_id = None
data_path = ""
collection_lock_file = "/nsls2/xf16id1/.lock"
okay_to_move_file = "/nsls2/xf16id1/.okay_to_move"
login_time = -1

def login(uname = None, pID = None, rID = None, debug=True, test_only=False,
          root_path='/nsls2/xf16id1', replace_froot=pilatus_data_dir, share_with=[]):
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
        proposal_id = "test"
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
    RE.md['run_id'] = run_id
    login_time = time.time()
    
    if test_only:
        path = f"{root_path}/data/"
    else:
        path = f"{root_path}/data/{current_cycle}/"
    rpath = str(proposal_id)+"/"+str(run_id)+"/"
    data_path = path + rpath
    makedirs(data_path, mode=0o0777)
    RE.md['data_path'] = data_path

    if replace_froot is not None:
        if replace_froot[-1]!="/":
            replace_froot+="/"
        data_path = data_path.replace(path, replace_froot)
        makedirs(data_path, mode=0o0777)
        #input(f"make sure {data_path} exists on the detector conputer. Hit any key to continue ...")
   
    if test_only:
        proc_path = data_path
    else:
        proc_path = f"{root_path}/experiments/{current_cycle}/{proposal_id}/{run_id}/"
    RE.md['proc_path'] = proc_path
    if not os.path.isdir(proc_path):
        makedirs(proc_path, mode=0o2755)
        makedirs(proc_path+"processed/")
  
    # if exp.h5 does not exist in proc_path, copy it from somewhere else
    # either the current directory, or from the proc_path of the last scan
    if not os.path.isfile(f"{proc_path}/exp.h5"):
        if os.path.isfile(f"{os.path.curdir}/exp.h5"):
            shutil.copy(f"{os.path.curdir}/exp.h5", f"{proc_path}")
        elif os.path.isfile(f"{db[-1].start['proc_path']}/exp.h5"):
            shutil.copy(f"{db[-1].start['proc_path']}/exp.h5", f"{proc_path}") 

    if len(share_with)>0:
        share_dir(proc_path, share_with)
    
    dw,mo,da,tt,yr = time.asctime().split()
    if not os.path.isdir(proc_path+"log"):
        os.mkdir(proc_path+"log")
    logfile = proc_path+("log/%s." % username)+yr+mo+("%02d_" % int(da))+tt.replace(':', '')
    ip = get_ipython()
    ip.magic("logstop")
    ip.magic("logstart -ort %s" % logfile)
    ip.logger.log_write(f"**LOGIN** {username} @ {time.asctime()}\n")    

    if debug:
        def print_time_callback(name, doc):
            if name =='start':
                t1 = time.time()
                print("#STARTDOC : {}".format(t1))
                print("#STARTDOC : {}".format(time.ctime(t1)))
        RE.subscribe(print_time_callback)


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
    
    # to be safe, need to have some kind of lock
    #get_lock()
    #if os.path.exists(link_to_data_path):
    #    os.remove(link_to_data_path)
    #os.symlink(data_path, link_to_data_path)

    
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

    del RE.md['owner']
    del RE.md['proposal_id']
    del RE.md['run_id']      
    del RE.md['data_path']      
    del RE.md['proc_path']      

    ip = get_ipython()
    ip.magic("logstop")
 
