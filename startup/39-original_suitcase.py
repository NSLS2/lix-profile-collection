#-------------------------------------------------------------------------
# Copyright (c) 2015-, Brookhaven National Laboratory
#
# Distributed under the terms of the BSD 3-Clause License.
#
# The full license is in the file LICENSE, distributed with this software.
#-------------------------------------------------------------------------

from collections.abc import Mapping
import numpy as np
import warnings
import h5py
import json
import copy, shutil
from databroker import Header

def conv_to_list(d): 
    if isinstance(d, float) or isinstance(d, int) or isinstance(d, str): 
        return [d] 
    elif isinstance(d, list):
        if not isinstance(d[0], list):
            return d 
    d1 = []
    for i in d:
        d1 += conv_to_list(i) 
    return d1 

def update_res_path(res_path, replace_res_path={}):
    for rp1,rp2 in replace_res_path.items():
        print("updating resource path ...")
        if rp1 in res_path:
            res_path = res_path.replace(rp1, rp2)  
    return res_path

def locate_h5_resource(res, replace_res_path, debug=False):
    """ this is intended to move h5 file created by Pilatus
        these files are originally saved on PPU RAMDISK, but should be moved to the IOC data directory
        this function will look for the file at the original location, and relocate the file first if it is there
        and return the h5 dataset
    """
    fn_orig = res["root"] + res["resource_path"]
    fn = update_res_path(fn_orig, replace_res_path)
    if debug:
        print(f"resource locations: {fn_orig} -> {fn}")
    
    if not(os.path.exists(fn_orig) or os.path.exists(fn)):
        print(f"could not location the resource at either {fn} or {fn_orig} ...")
        raise Exception
    if os.path.exists(fn_orig) and os.path.exists(fn) and fn_orig!=fn:
        print(f"both {fn} and {fn_orig} exist, resolve the conflict manually first ..." )
        raise Exception
    if not os.path.exists(fn):
        fdir = os.path.dirname(fn)
        if not os.path.exists(fdir):
            makedirs(fdir, mode=0o2775)
        if debug:
            print(f"copying {fn_orig} to {fdir}")
        tfn = fn+"_partial"
        shutil.copy(fn_orig, tfn)
        os.rename(tfn, fn)
        os.remove(fn_orig)
    
    hf5 = h5py.File(fn, "r")
    return hf5,hf5["/entry/data/data"]


def hdf5_export(headers, filename, debug=False,
           stream_name=None, fields=None, bulk_h5_res=True,
           timestamps=True, use_uid=True, db=None, replace_res_path={}):
    """
    Create hdf5 file to preserve the structure of databroker.

    Parameters
    ----------
    headers : a Header or a list of Headers
        objects retruned by the Data Broker
    filename : string
        path to a new or existing HDF5 file
    stream_name : string, optional
        None means save all the data from each descriptor, i.e., user can define stream_name as primary,
        so only data with descriptor.name == primary will be saved.
        The default is None.
    fields : list, optional
        whitelist of names of interest; if None, all are returned;
        This is consistent with name convension in databroker.
        The default is None.
    timestamps : Bool, optional
        save timestamps or not
    use_uid : Bool, optional
        Create group name at hdf file based on uid if this value is set as True.
        Otherwise group name is created based on beamline id and run id.
    db : databroker object, optional
        db should be included in hdr.
    replace_res_path: in case the resource has been moved, specify how the path should be updated
        e.g. replace_res_path = {"exp_path/hdf": "nsls2/xf16id1/data/2022-1"}
        
    Revision 2021 May
        Now that the resource is a h5 file, copy data directly from the file 
        
    """
    if isinstance(headers, Header):
        headers = [headers]

    with h5py.File(filename, "w") as f:
        #f.swmr_mode = True # Unable to start swmr writing (file superblock version - should be at least 3)
        for header in headers:
            try:
                db = header.db
            except AttributeError:
                pass
            if db is None:
                raise RuntimeError('db is not defined in header, so we need to input db explicitly.')
                
            res_docs = {}
            for n,d in header.documents():
                if n=="resource":
                    res_docs[d['uid']] = d
            if debug:
                print("res_docs:\n", res_docs)
                    
            try:
                descriptors = header.descriptors
            except KeyError:
                warnings.warn("Header with uid {header.uid} contains no "
                              "data.".format(header), UserWarning)
                continue
            if use_uid:
                top_group_name = header.start['uid']
            else:
                top_group_name = 'data_' + str(header.start['scan_id'])
            group = f.create_group(top_group_name)
            _safe_attrs_assignment(group, header)
            for i, descriptor in enumerate(descriptors):
                # make sure it's a dictionary and trim any spurious keys
                descriptor = dict(descriptor)
                if stream_name:
                    if descriptor['name'] != stream_name:
                        continue
                descriptor.pop('_name', None)
                if debug:
                    print(f"processing stream {stream_name}")

                if use_uid:
                    desc_group = group.create_group(descriptor['uid'])
                else:
                    desc_group = group.create_group(descriptor['name'])

                data_keys = descriptor['data_keys']

                _safe_attrs_assignment(desc_group, descriptor)

                # fill can be bool or list
                events = list(header.events(stream_name=descriptor['name'], fill=False))

                res_dict = {}
                for k,v in list(events[0]['data'].items()):
                    if not isinstance(v,str):
                        continue
                    if v.split('/')[0] in res_docs.keys():
                        res_dict[k] = []
                        for ev in events:
                            res_uid = ev['data'][k].split("/")[0]
                            if not res_uid in res_dict[k]:
                                res_dict[k].append(res_uid)

                if debug:
                    print("res_dict:\n", res_dict)

                event_times = [e['time'] for e in events]
                desc_group.create_dataset('time', data=event_times,
                                          compression='gzip', fletcher32=True)
                data_group = desc_group.create_group('data')
                if timestamps:
                    ts_group = desc_group.create_group('timestamps')

                for key, value in data_keys.items():
                    print(f"processing {key} ...")
                    if fields is not None:
                        if key not in fields:
                            print("   skipping ...")
                            continue
                    print(f"creating dataset for {key} ...")
                    if timestamps:
                        timestamps = [e['timestamps'][key] for e in events]
                        ts_group.create_dataset(key, data=timestamps,
                                                compression='gzip',
                                                fletcher32=True)

                    if key in list(res_dict.keys()):
                        res = res_docs[res_dict[key][0]]
                        print(f"preocessing resource ...\n", res)

                        # pilatus data, change the path from ramdisk to IOC data directory
                        if key in ["pil1M_image", "pilW2_image"]:
                            rp = {pilatus_data_dir: data_destination}

                        if res['spec'] == "AD_HDF5" and bulk_h5_res:
                            rawdata = None
                            N = len(res_dict[key])
                            print(f"copying data from source h5 file(s) directly, N={N} ...")
                            if N==1:
                                hf5,data = locate_h5_resource(res_docs[res_dict[key][0]], replace_res_path=rp, debug=debug)
                                data_group.copy(data, key)
                                hf5.close()
                                dataset = data_group[key]
                            else: # ideally this should never happen, only 1 hdf5 file/resource per scan
                                for i in range(N):
                                    hf5,data = locate_h5_resource(res_docs[res_dict[key][i]])
                                    if i==0:
                                        dataset = data_group.create_dataset(
                                                key, shape=(N, *data.shape), 
                                                compression=data.compression,
                                                chunks=(1, *data.chunks))
                                    dataset[i,:] = data
                                    hf5.close()
                        else:
                            print(f"getting resource data using handlers ...")
                            rawdata = header.table(stream_name=descriptor['name'], 
                                                   fields=[key], fill=True)[key]   # this returns the time stamps as well
                    else:
                        print(f"compiling resource data from individual events ...")
                        rawdata = [e['data'][key] for e in events]

                    if rawdata is not None:
                        data = np.array(rawdata)

                        if value['dtype'].lower() == 'string':  # 1D of string
                            data_len = len(data[0])
                            data = data.astype('|S'+str(data_len))
                            dataset = data_group.create_dataset(
                                key, data=data, compression='gzip')
                        elif data.dtype.kind in ['S', 'U']:
                            # 2D of string, we can't tell from dytpe, they are shown as array only.
                            if data.ndim == 2:
                                data_len = 1
                                for v in data[0]:
                                    data_len = max(data_len, len(v))
                                data = data.astype('|S'+str(data_len))
                                dataset = data_group.create_dataset(
                                    key, data=data, compression='gzip')
                            else:
                                raise ValueError(f'Array of str with ndim >= 3 can not be saved: {key}')
                        else:  # save numerical data
                            try:
                                if isinstance(rawdata, list):
                                    blk = rawdata[0]
                                else:
                                    blk = rawdata[1]
                                if isinstance(blk, np.ndarray): # detector image
                                    data = np.vstack(rawdata)
                                    chunks = np.ones(len(data.shape), dtype=int)
                                    n = len(blk.shape)
                                    if chunks[-1]<10:
                                        chunks[-3:] = data.shape[-3:]
                                    else:
                                        chunks[-2:] = data.shape[-2:]
                                    chunks = tuple(chunks)
                                    print("data shape: ", data.shape, "     chunks: ", chunks)
                                    dataset = data_group.create_dataset(
                                        key, data=data,
                                        compression='gzip', fletcher32=True, chunks=chunks)
                                else: # motor positions etc.
                                    data = np.array(conv_to_list(rawdata)) # issue with list of lists
                                    chunks = False
                                    dataset = data_group.create_dataset(
                                        key, data=data,
                                        compression='gzip', fletcher32=True)
                            except:
                                raise
                            #    print("failed to convert data: ")
                            #    print(np.array(conv_to_list(rawdata)))
                            #    continue

                    # Put contents of this data key (source, etc.)
                    # into an attribute on the associated data set.
                    _safe_attrs_assignment(dataset, dict(value))


def _clean_dict(d):
    d = dict(d)
    for k, v in list(d.items()):
        # Store dictionaries as JSON strings.
        if isinstance(v, Mapping):
            d[k] = _clean_dict(d[k])
            continue
        try:
            json.dumps(v)
        except TypeError:
            d[k] = str(v)
    return d


def _safe_attrs_assignment(node, d):
    d = _clean_dict(d)
    for key, value in d.items():
        # Special-case None, which fails too late to catch below.
        if value is None:
            value = 'None'
        # Try storing natively.
        try:
            node.attrs[key] = value
        # Fallback: Save the repr, which in many cases can be used to
        # recreate the object.
        except TypeError:
            node.attrs[key] = json.dumps(value)

def filter_fields(headers, unwanted_fields):
    """
    Filter out unwanted fields.

    Parameters
    ----------
    headers : doct.Document or a list of that
        returned by databroker object
    unwanted_fields : list
        list of str representing unwanted filed names

    Returns
    -------
    set:
        set of selected names
    """
    if isinstance(headers, Header):
        headers = [headers]
    whitelist = set()
    for header in headers:
        for descriptor in header.descriptors:
            good = [key for key in descriptor.data_keys.keys()
                    if key not in unwanted_fields]
            whitelist.update(good)
    return whitelist
