from suitcase import hdf5  #,nexus # available in suitcase 0.6

import h5py,json,os
import threading
import numpy as np
import epics,socket
from collections import deque

global default_data_path_root
global substitute_data_path_root
global CBF_replace_data_path
global DET_replace_data_path

"""
def add_to_processing_queue(uid):
    epics.caput('XF:16IDC-DT{Det:SAXS}cam1:filemover.add_to_queue', uid)

def get_from_processing_queue():
    epics.caput('XF:16IDC-DT{Det:SAXS}cam1:filemover.get_from_queue', 1)
    ret = epics.caget('XF:16IDC-DT{Det:SAXS}cam1:filemover.current_item', as_string=True, count=4096)
    return ret # [s for s in ret.split(' ') if s!='']

def set_dest_h5_dir(dest):
    if dest!='' and not os.path.exists(dest):
        raise Exception(f'{dest_dir} does not exist.')
    epics.caput('XF:16IDC-DT{Det:SAXS}cam1:filemover.dest_h5_dir', dest)
    
def get_file_path(header):
    for fd in list(header.fields()):
        if fd.find('file_path')>=0:
            return header.table(fields=[fd])[fd][1]
    return None
"""

                    
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
    
def pack_h5(uids, dest_dir='', fn=None, fix_sample_name=True, 
            attach_uv_file=False, delete_old_file=False,
            fields=[#'em2_current1_mean_value', 'em2_current2_mean_value',
                    'em1_sum_all_mean_value', 'em2_sum_all_mean_value',
                    'pil1M_image', 'pilW1_image', 'pilW2_image', 
                    'pil1M_ext_image', 'pilW1_ext_image', 'pilW2_ext_image']):
    """ if only 1 uid is given, use the sample name as the file name
        any metadata associated with each uid will be retained (e.g. sample vs buffer)
    """
    if isinstance(uids, list):
        if fn is None:
            raise Exception("a file name must be given for a list of uids.")
        headers = [db[u] for u in uids]
        pns = [h.start.plan_name for h in headers]
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

    fds0 = headers[0].fields()
    # only these fields are considered relevant to be saved in the hdf5 file
    fds = list(set(fds0) & set(fields))
    if 'motors' in list(headers[0].start.keys()):
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
    hdf5.export(headers, fn, fields=fds, use_uid=False) #, mds= db.mds, use_uid=False) 
    
    # by default the groups in the hdf5 file are named after the scan IDs
    if fix_sample_name:
        h5_fix_sample_name(fn)
        
    if attach_uv_file:
        # by default the UV file should be saved in /GPFS/xf16id/Windows/
        h5_attach_hplc(fn, '/GPFS/xf16id/Windows/hplc_export.txt')
    
    return fn


def h5_attach_hplc(fn_h5, fn_hplc, grp_name=None):
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
    grp = f["%s/hplc/data" % grp_name]
    
    hdstr, dhplc = readShimadzuDatafile(fn_hplc)
    
    if grp.attrs.get('header') == None:
        grp.attrs.create("header", np.asarray(hdstr, dtype=np.string_))
    else:
        grp.attrs.modify("header", np.asarray(hdstr, dtype=np.string_))
    
    existing_keys = list(grp.keys())
    for k in dhplc.keys():
        d = np.asarray(dhplc[k]).T
        if k in existing_keys:
            print("warning: %s already exists." % k)
        dset = grp.require_dataset(k, d.shape, d.dtype)
        dset[:] = d
    
    f.close()
