import os,stat,time
from IPython import get_ipython

username = None
proposal_id = None
run_id = None
data_path = None
collection_lock_file = "/GPFS/xf16id/.lock"
okay_to_move_file = "/GPFS/xf16id/.okay_to_move"

current_cycle = '2018-3'

def login(uname = None, pID = None, rID = None, debug=True, 
          root_path='/GPFS/xf16id', create_proc_dir=False):
    """Ask the user for his credentials and proposal information for the data collection"""
    #TODO: Use PASS and LDAP integration when possible.
    global username
    global proposal_id
    global run_id
    global data_path 

    correct_info = False
    if uname != None and pID!=None and rID!=None: 
      username = uname
      proposal_id = pID
      run_id = rID
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
    
    path = root_path + '/exp_path/'
    rpath = str(proposal_id)+"/"+str(run_id)+"/"
    data_path = path + rpath
    makedirs(data_path)
    
    if create_proc_dir:
        proc_path = f"{root_path}/Processing/{current_cycle}/{proposal_id}/{run_id}/"
        makedirs(proc_path)
        makedirs(proc_path+"processed/")
    
    RE.md['data_path'] = data_path
    
    dw,mo,da,tt,yr = time.asctime().split()
    logfile = data_path+("log-%s." % username)+yr+mo+("%02d_" % int(da))+tt
    ip = get_ipython()
    ip.magic("logstop")
    ip.magic("logstart -ort %s" % logfile)
    
    if debug:
        def print_time_callback(name, doc):
            if name =='start':
                t1 = time.time()
                print("#STARTDOC : {}".format(t1))
                print("#STARTDOC : {}".format(time.ctime(t1)))
        RE.subscribe(print_time_callback)


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
    #link_to_data_path = "/GPFS/xf16id/current_data"
    
    if username==None or proposal_id==None or run_id==None:
        login()
    
    # to be safe, need to have some kind of lock
    #get_lock()
    #if os.path.exists(link_to_data_path):
    #    os.remove(link_to_data_path)
    #os.symlink(data_path, link_to_data_path)

    
def logoff():
    global username
    global proposal_id
    global run_id
    global data_path 

    """Clear the login information"""
    if (input("Are you sure you want to logout? [Y, N]: ") in ['Y', 'y']):
        username = None
        proposal_id = None
        run_id = None
        data_path = None

        del RE.md['owner']
        del RE.md['proposal_id']
        del RE.md['run_id']      
        del RE.md['data_path']      

        ip = get_ipython()
        ip.magic("logstop")
 
