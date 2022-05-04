import h5py,json,os
import threading
import numpy as np
import epics,socket
from collections import deque

global proc_path

def lsh5(hd, prefix='', top_only=False):
    if top_only:
        print(list(hd.keys()))
        return
    for k in list(hd.keys()):
        print(prefix, k)
        if isinstance(hd[k], h5py.Group):
            print(list(hd[k].attrs.items()))
            lsh5(hd[k], prefix+"==")
            
def h5_fix_sample_name(fn_h5):
    """ the hdf5 file is assumed to have top-level groups that each corresponds to a sample
    """
    f = h5py.File(fn_h5, "r+")
    grps = list(f.keys())
    for g in grps:
        header = json.loads(f[g].attrs.get('start'))
        if 'sample_name' in header.keys():
            sn = header['sample_name']
            f.move(g, sn)
    f.close()

# maximum process allowed to be packing hdf5 files (may use a lot of memory)
max_packing_processes = 3
pack_h5_lock = threading.Semaphore(max_packing_processes)

def pack_h5_with_lock(*args, **kwargs):
    pack_h5_lock.acquire()
    try:
        ret = pack_h5(*args, **kwargs)
    except Exception as e:
        print(f"An error occured when packing h5: {e}")
        ret = None
    pack_h5_lock.release()    
    return ret


def compile_replace_res_path(h):
    """ protocol prior to May 2022:
            md['data_path'] specifies the directories all data files are supposed to go
                e.g. /nsls2/xf16id1/data/2022-1/310121/308824
            the original location of the data is recorded in the databroker, but not in the meta data
            however, this location should follow the format of the {pilatus_data_dir}/{proposal_id}/{run_id} 
        protocol since May 2022:
            md['data_path'] specifies where all IOC data are supposed to go
                e.g. /nsls2/data/lix/legacy/%s/2022-1/310032/test
            md['pilatus']['ramdisk'] specifies where the Pilatus data are originally saved
                e.g. /exp_path/hdf
    """
    md = h.start
    ret = {}
    dpath = md['data_path']
    try:
        ret[md['pilatus']['ramdisk']] = dpath.split("%s")[0]
    except:
        cycle_id = re.search("20[0-9][0-9]-[0-9]", dpath)[0]
        ret[pilatus_data_dir] = dpath.split(cycle_id)[0]+cycle_id
    
    return ret

def pack_h5(uids, dest_dir='', fn=None, fix_sample_name=True, stream_name=None, 
            attach_uv_file=False, delete_old_file=True, include_motor_pos=True, debug=False,
            fields=['em2_current1_mean_value', 'em2_current2_mean_value',
                    'em1_sum_all_mean_value', 'em2_sum_all_mean_value', 'em2_ts_SumAll', 'em1_ts_SumAll',
                    'xsp3_spectrum_array_data', "pilatus_trigger_time",
                    'pil1M_image', 'pilW1_image', 'pilW2_image', 
                    'pil1M_ext_image', 'pilW1_ext_image', 'pilW2_ext_image'], replace_res_path={}):
    """ if only 1 uid is given, use the sample name as the file name
        any metadata associated with each uid will be retained (e.g. sample vs buffer)
        
        to avoid multiple processed requesting packaging, only 1 process is allowed at a given time
        this is i
    """
    if isinstance(uids, list):
        if fn is None:
            raise Exception("a file name must be given for a list of uids.")
        headers = [db[u] for u in uids]
        pns = [h.start['plan_name'] for h in headers]
        if not (pns[1:]==pns[:-1]):
            raise Exception("mixed plan names in uids: %s" % pns)
    else:
        header = db[uids]
        if fn is None:
            if "sample_name" in list(header.start.keys()):
                fn = header.start['sample_name']
            else:
                fds = header.fields()
                # find the first occurance of _file_file_name in fields
                f = next((x for x in fds if "_file_file_name" in x), None)
                if f is None:
                    raise Exception("could not automatically select a file name.")
                fn = header.table(fields=[f])[f][1]
        headers = [header]

    # if replace_res_path is not specified, try to figure out whether it is necessary
    if len(replace_res_path)==0: 
        replace_res_path = compile_replace_res_path(headers[0])
        
    fds0 = headers[0].fields()
    # only these fields are considered relevant to be saved in the hdf5 file
    fds = list(set(fds0) & set(fields))
    if 'motors' in list(headers[0].start.keys()) and include_motor_pos:
        for m in headers[0].start['motors']:
            fds += [m] #, m+"_user_setpoint"]
    
    if fn[-3:]!='.h5':
        fn += '.h5'

    if dest_dir!='':
        if not os.path.exists(dest_dir):
            raise Exception(f'{dest_dir} does not exist.')
        fn = dest_dir+'/'+fn
        
    if delete_old_file:
        try:
            os.remove(fn)
        except OSError:
            pass
        
    print(fds)
    hdf5_export(headers, fn, fields=fds, stream_name=stream_name, use_uid=False, 
                replace_res_path=replace_res_path, debug=debug) #, mds= db.mds, use_uid=False) 
    
    # by default the groups in the hdf5 file are named after the scan IDs
    if fix_sample_name:
        h5_fix_sample_name(fn)
        
    if attach_uv_file:
        # by default the UV file should be saved in /nsls2/xf16id1/Windows/
        # ideally this should be specified, as the default file is overwritten quickly
        h5_attach_hplc(fn, '/nsls2/xf16id1/Windows/hplc_export.txt')
    
    print(f"finished packing {fn} ...")
    return fn


def h5_attach_hplc(fn_h5, fn_hplc, chapter_num=-1, grp_name=None):
    """ the hdf5 is assumed to contain a structure like this:
        LIX_104
        == hplc
        ==== data
        == primary (em, scattering patterns, ...)
        
        attach the HPLC data to the specified group
        if the group name is not give, attach to the first group in the h5 file
    """
    f = h5py.File(fn_h5, "r+")
    if grp_name == None:
        grp_name = list(f.keys())[0]

    hdstr, dhplc = readShimadzuDatafile(fn_hplc, chapter_num=chapter_num )
    # 3rd line of the header contains the HPLC data file name, which is based on the sample name 
    sname = hdstr.split('\n')[2].split('\\')[-1][:-4]
    if grp_name!=sname:
        print(f"mismatched sample name: {sname} vs {grp_name}")
        f.close()
        return
    
    # this group is created by suitcase if using flyer-based hplc_scan
    # otherwise it has to be created first
    # it is also possible that there was a previous attempt to populate the data
    # but the data source/shape is incorrect -> delete group first
    if 'hplc' in f[f"{grp_name}"].keys():
        grp = f["%s/hplc/data" % grp_name]
    else:
        grp = f.create_group(f"{grp_name}/hplc/data")
    
    if grp.attrs.get('header') == None:
        grp.attrs.create("header", np.asarray(hdstr, dtype=np.string_))
    else:
        grp.attrs.modify("header", np.asarray(hdstr, dtype=np.string_))
    
    existing_keys = list(grp.keys())
    for k in dhplc.keys():
        d = np.asarray(dhplc[k]).T
        if k in existing_keys:
            print("warning: %s already exists, deleting ..." % k)
            del grp[k]
        dset = grp.require_dataset(k, d.shape, d.dtype)
        dset[:] = d
    
    f.close()

from py4xs.detector_config import create_det_from_attrs
from py4xs.hdf import h5xs,h5exp    
from lixtools.hdf import h5sol_HPLC,h5sol_HT
from lixtools.atsas import gen_report
import json

import socket
packing_queue_sock_port = 9999

# process locally
def send_to_packing_queue(uid, data_type, froot=data_file_path.gpfs, move_first=False):
    """ data_type must be one of ["scan", "flyscan", "HPLC", "sol", "multi", "mscan"]
        single uid only for "scan", "flyscan", "HPLC"
        uids must be concatenated using '|' for "multi" and "sol"
        if move_first is True, move the files from RAMDISK to GPFS first, otherwise the RAMDISK
            may fill up since only one pack_h5 process is allow
    """
    if data_type not in ["scan", "flyscan", "HPLC", "multi", "sol", "mscan", "mfscan"]:
        raise Exception("invalid data type: {datatype}, valid options are scan and HPLC.")

    #msg = f"{datatype}::{uid}::{proc_path}::{froot.name}::{move_first}"
    #data_type,uid,path,frn,t = msg.split("::") 

    if data_type not in ["multi", "sol", "mscan", "mfscan"]: # single UID
        if 'exit_status' not in db[uid].stop.keys():
            print(f"in complete header for {uid}.")
            return
        if db[uid].stop['exit_status'] != 'success': # the scan actually finished
            print(f"scan {uid} was not successful.")
            return 

    threading.Thread(target=pack_and_process, args=(data_type,uid,proc_path,move_first,)).start() 
    print("processing thread started ...")                    
        

def send_to_packing_queue_remote(uid, datatype, froot=data_file_path.gpfs, move_first=False):
    """ data_type must be one of ["scan", "flyscan", "HPLC", "sol", "multi", "mscan"]
        single uid only for "scan", "flyscan", "HPLC"
        uids must be concatenated using '|' for "multi" and "sol"
        if move_first is True, move the files from RAMDISK to GPFS first, otherwise the RAMDISK
            may fill up since only one pack_h5 process is allow
    """
    if datatype not in ["scan", "flyscan", "HPLC", "multi", "sol", "mscan", "mfscan"]:
        raise Exception("invalid data type: {datatype}, valid options are scan and HPLC.")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM) 
    s.connect(('xf16id-srv1', packing_queue_sock_port))
    msg = f"{datatype}::{uid}::{proc_path}::{froot.name}::{move_first}"
    s.send(msg.encode('ascii'))
    s.close()

def pack_and_process(data_type, uid, dest_dir):
    # useful for moving files from RAM disk to GPFS during fly scans
    # 
    # assume other type of data are saved on RAM disk as well (GPFS not working for WAXS2)
    # these data must be moved manually to GPFS
    #global pilatus_trigger_mode  #,CBF_replace_data_path 
    
    print(f"packing: {data_type}, {uid}, {dest_dir}")
    t0 = time.time()
    # if the dest_dir contains exp.h5, read detectors/qgrid from it
    try:
        dt_exp = h5exp(dest_dir+'/exp.h5')
    except:
        dt_exp = None

    dir_name = None
    
    if data_type in ["multi", "sol", "mscan", "mfscan"]:
        uids = uid.split('|')
        if data_type=="sol":
            sb_dict = json.loads(uids.pop())
        ## assume that the meta data contains the holderName
        if 'holderName' not in list(db[uids[0]].start.keys()):
            print("cannot find holderName from the header, using tmp.h5 as filename ...")
            fh5_name = "tmp.h5"
        else:
            dir_name = db[uids[0]].start['holderName']
            fh5_name = dir_name+'.h5'
        fn = pack_h5_with_lock(uids, dest_dir, fn="tmp.h5")
        if fn is not None and dt_exp is not None and data_type!="mscan":
            print('processing ...')
            if data_type=="sol":    
                dt = h5sol_HT(fn, [dt_exp.detectors, dt_exp.qgrid])
                dt.assign_buffer(sb_dict)
                dt.process(filter_data=True, sc_factor="auto", debug='quiet')
                #dt.export_d1s(path=dest_dir+"/processed/")
            elif data_type=="multi":
                dt = h5xs(fn, [dt_exp.detectors, dt_exp.qgrid], transField='em2_sum_all_mean_value')
                dt.load_data(debug="quiet")
            elif data_type=="mfscan":
                dt = h5xs(fn, [dt_exp.detectors, dt_exp.qgrid])
                dt.load_data(debug="quiet")
            dt.fh5.close()
            del dt,dt_exp            
            if fh5_name!="tmp.h5":  # temporary fix, for some reason other processes cannot open the packed file
                os.system(f"cd {dest_dir} ; cp tmp.h5 {fh5_name} ; rm tmp.h5")
            if data_type=="sol":    
                try:
                    gen_report(fh5_name)
                except:
                    pass
    elif data_type=="HPLC":
        uids = [uid]
        fn = pack_h5_with_lock(uid, dest_dir=dest_dir, attach_uv_file=True)
        if fn is not None and dt_exp is not None:
            print('procesing ...')
            dt = h5sol_HPLC(fn, [dt_exp.detectors, dt_exp.qgrid])
            dt.process(debug='quiet')
            dt.fh5.close()
            del dt,dt_exp
    elif data_type=="flyscan" or data_type=="scan":
        uids = [uid]
        fn = pack_h5_with_lock(uid, dest_dir=dest_dir)
    else:
        print(f"invalid data type: {data_type} .")
        return

    if fn is None:
        return # packing unsuccessful, 
    print(f"{time.asctime()}: finished packing/processing, total time lapsed: {time.time()-t0:.1f} sec ...")

            
def process_packing_queue():
    """ this should only run on xf16idc-gpu1, moved to srv1 Mar 2022
        needed for HPLC run and microbeam mapping
    """    
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) 
    host = socket.gethostname()                           
    if host!='xf16id-srv1' and host!="xf16id-srv1.nsls2.bnl.local":
        raise Exception(f"this function can only run on xf16id-srv1, not {host}.")
    serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversocket.bind(('xf16id-srv1', packing_queue_sock_port))  
    serversocket.listen(5)
    print('listening ...')
    
    while True:
        clientsocket,addr = serversocket.accept()      
        print(f"{time.asctime()}: got a connection from {addr} ...")
        msg = clientsocket.recv(8192).decode()
        print(msg)
        clientsocket.close()
        data_type,uid,path,frn,t = msg.split("::") 
        if t is True:
            move_first = True
        else:
            move_first = False
        
        if data_type not in ["multi", "sol", "mscan", "mfscan"]: # single UID
            if 'exit_status' not in db[uid].stop.keys():
                print(f"in complete header for {uid}.")
                return
            if db[uid].stop['exit_status'] != 'success': # the scan actually finished
                print(f"scan {uid} was not successful.")
                return 

        threading.Thread(target=pack_and_process, args=(data_type,uid,path,move_first,)).start() 
        print("processing thread started ...")            


