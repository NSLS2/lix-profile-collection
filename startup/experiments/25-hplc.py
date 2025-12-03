print(f"Loading {__file__}...")
import socket
import numpy as np
from time import sleep
import signal
#from import pumpID, pump_SSI
#from VICI_Valves import VICI_ID, VICI_valves
import itertools
import pathlib, subprocess
windows_ip = '10.66.123.226'

#TRP=pump_SSI(pumpID.RegenPump.address, pumpID.RegenPump.port)
#VV = VICI_valves()


'''
       
def CreateAgilentSeqFile(spreadsheet_fn, batchID, sheet_name='Samples'):
    
    """
    Creates the agilent sequence file from the spreadsheet. User input is batchID, sample_name and method for hplc. The other columns are necessary for generating the proper formatted sequence file
    """
    strFields=["Vial", "Sample Name", "Sample Type", "Acq. method", "Proc. method", "Data file", "Buffer", "Valve Position"]
    numFields=["Volume"]
    dd=parseSpreadsheet(spreadsheet_fn, sheet_name=sheet_name, return_dataframe=False)
    print(f"this is {dd}")
    autofillSpreadsheet(dd, fields=["batchID"])
    print(dd['batchID'].keys())
    print(dd['batchID'].values())
    print(dd['Valve Position'].values())
    
    if proposal_id is None or run_id is None:
        print("need to login first ...")
        login()
    
    ridx=[i for i in dd['batchID'].keys() if dd['batchID'][i]==batchID]
    print(f"{ridx} this is ridx")

    
    samples = {}
    dfile = f"{current_cycle}/{proposal_id}/{run_id}/<S>" 
    dd["Data File"] = {}
    dd["Sample Type"] = {}
    valve_position = {}
        
    for i in ridx:
        for f in numFields:
            if not (isinstance(dd[f][i], int or isintance(dd[f][i], float))):
                raise Exception(f"not a numeric value for {f}: {dd[f][i].values()}, replace with number")
        valve_position[i] = dd["Valve Position"][i]
        print(valve_position)
        sn = dd['Sample Name'][i]
        samples[sn] = {"acq time": dd['Run Time'][i], 
                       "valve_position":valve_position[i],
                       "md": {"Column type": dd['Column type'][i],
                              "Injection Volume (ul)": dd['Volume'][i],
                              "Flow Rate (ml_min)": dd['Flow Rate'][i],
                              "Sample buffer":dd['Buffer'][i],
                              "Valve Position":valve_position[i]}
                      }
        dd["Data File"][i] = dfile
        dd["Valve Position"][i]
        dd["Sample Type"][i] = "Sample"
    sequence_path="/nsls2/data4/lix/legacy/HPLC/Agilent/"
    df=pd.DataFrame.from_dict(dd, orient='columns')
    df[df['batchID']==batchID].to_csv(f"{sequence_path}sequence_table.csv", index=False, encoding="ASCII",
                    columns=["Vial", "Sample Name", "Sample Type", "Volume", "Inj/Vial", "Acq. method", "Proc. method", "Data File" ])
    source_file = f"{sequence_path}"+'sequence_table.csv'

    return samples, valve_position  



def run_hplc_from_spreadsheet(spreadsheet_fn, batchID, sheet_name='Samples', exp=1, shutdown=False):
    batch_fn = '/nsls2/data/lix/legacy/HPLC/Agilent/sequence_table.csv'
    samples, valve_position = CreateAgilentSeqFile(spreadsheet_fn, batchID, sheet_name=sheet_name)
    print(f"HPLC sequence file has been created in: {batch_fn}")
    print("Make sure you have selected the correct valve position for column type!")
    input("Please start Sequence in Agilent software by importing sequence_table.csv (under sequence tab), click run, then come back to this machine and then hit enter:")
    for sn in samples.keys():
        VV.switch_10port_valve(pos=samples[sn]["md"]["Valve Position"])
        print(f"Switching valve to position {samples[sn]['md']['Valve Position']}!")
        caput('XF:16IDC-ES:{HPLC}SampleName', sn)
        print(f"collecting data for {sn} ...")

            #print(f"Switching to valve position {pos}!")
            #switch_10port_valve(pos=pos)
        # for hardware multiple trigger, the interval between triggers is slightly longer
        #    than exp. but this extra time seems to fluctuates. it might be safe not to include
        #    it in the caulcation of nframes
        
        collect_hplc(sn, exp=exp, nframes=int(samples[sn]["acq time"]*60/exp), md={'HPLC': samples[sn]['md']})   
        uid=db[-1].start['uid']
        send_to_packing_queue(uid, "HPLC")
    pil.use_sub_directory()
    move_hplc_files(current_sample=current_sample)
#    h5_attach_hplc(fn_h5=None)
    
    print('Sequence collection finished for %s from %s' % (batchID,spreadsheet_fn))

####Running HPLC 


def CreateAgilentSeqFile(spreadsheet_fn, batchID, sheet_name='Samples'):
    
    """
    Creates the agilent sequence file from the spreadsheet. User input is batchID, sample_name and method for hplc. The other columns are necessary for generating the proper formatted sequence file
    """
    strFields=["Vial", "Sample Name", "Sample Type", "Acq. method", "Proc. method", "Data file", "Buffer", "Valve Position"]
    numFields=["Volume"]
    dd=parseSpreadsheet(spreadsheet_fn, sheet_name=sheet_name, return_dataframe=False)
    print(f"this is {dd}")
    autofillSpreadsheet(dd, fields=["batchID"])
    print(dd['batchID'].keys())
    print(dd['batchID'].values())
    print(dd['Valve Position'].values())
    
    if proposal_id is None or run_id is None:
        print("need to login first ...")
        login()
    
    ridx=[i for i in dd['batchID'].keys() if dd['batchID'][i]==batchID]
    print(f"{ridx} this is ridx")

    
    samples = {}
    dfile = f"{current_cycle}/{proposal_id}/{run_id}/<S>" 
    dd["Data File"] = {}
    dd["Sample Type"] = {}
    valve_position = {}
        
    for i in ridx:
        for f in numFields:
            if not (isinstance(dd[f][i], int or isintance(dd[f][i], float))):
                raise Exception(f"not a numeric value for {f}: {dd[f][i].values()}, replace with number")
        valve_position[i] = dd["Valve Position"][i]
        print(valve_position)
        sn = dd['Sample Name'][i]
        samples[sn] = {"acq time": dd['Run Time'][i], 
                       "valve_position":valve_position[i],
                       "md": {"Column type": dd['Column type'][i],
                              "Injection Volume (ul)": dd['Volume'][i],
                              "Flow Rate (ml_min)": dd['Flow Rate'][i],
                              "Sample buffer":dd['Buffer'][i],
                              "Valve Position":valve_position[i]}
                      }
        dd["Data File"][i] = dfile
        dd["Valve Position"][i]
        dd["Sample Type"][i] = "Sample"
    sequence_path="/nsls2/data4/lix/legacy/HPLC/Agilent/"
    df=pd.DataFrame.from_dict(dd, orient='columns')
    df[df['batchID']==batchID].to_csv(f"{sequence_path}sequence_table.csv", index=False, encoding="ASCII",
                    columns=["Vial", "Sample Name", "Sample Type", "Volume", "Inj/Vial", "Acq. method", "Proc. method", "Data File" ])
    source_file = f"{sequence_path}"+'sequence_table.csv'
    destination_loc = "xf16id@10.66.123.226:C:/CDSProjects/HPLC/"
    
    try:
            ssh_key = str(pathlib.Path.home())+"/.ssh/id_rsa.pub"
            if not os.path.isfile(ssh_key):
                raise Exception(f"{ssh_key} does not exist!")
            cmd = ["scp", "/nsls2/data4/lix/legacy/HPLC/Agilent/sequence_table.csv", destination_loc] ##hardcoded path for sequence file
            #print(cmd)
            subprocess.run(cmd)
            print("Sequence_table sucessfully sent")
    except Exception as e:
        print(f"SCP transfer has failed for {cmd}!")
    
    return samples, valve_position  


        
def run_hplc_from_spreadsheet(spreadsheet_fn, batchID, sheet_name='Samples', exp=1, shutdown=False):
    batch_fn = '/nsls2/data/lix/legacy/HPLC/Agilent/sequence_table.csv'
    samples, valve_position = CreateAgilentSeqFile(spreadsheet_fn, batchID, sheet_name=sheet_name)
    print(f"HPLC sequence file has been created in: {batch_fn}")
    print("Make sure you have selected the correct valve position for column type!")
    input("Please start Sequence in Agilent software by importing sequence_table.csv (under sequence tab), click run, then come back to this machine and then hit enter:")
    for sn in samples.keys():
        VV.switch_10port_valve(pos=samples[sn]["md"]["Valve Position"])
        print(f"Switching valve to position {samples[sn]['md']['Valve Position']}!")
        caput('XF:16IDC-ES:{HPLC}SampleName', sn)
        print(f"collecting data for {sn} ...")

            #print(f"Switching to valve position {pos}!")
            #switch_10port_valve(pos=pos)
        # for hardware multiple trigger, the interval between triggers is slightly longer
        #    than exp. but this extra time seems to fluctuates. it might be safe not to include
        #    it in the caulcation of nframes
        
        collect_hplc(sn, exp=exp, nframes=int(samples[sn]["acq time"]*60/exp), md={'HPLC': samples[sn]['md']})   
        uid=db[-1].start['uid']
        send_to_packing_queue(uid, "HPLC")
    pil.use_sub_directory()
    move_hplc_files(current_sample=current_sample)
#    h5_attach_hplc(fn_h5=None)
    
    print('Sequence collection finished for %s from %s' % (batchID,spreadsheet_fn))

'''
def scp_transfer(cmd):
        """To handle copying files from lustre to machine running Agilent software and vice versa"""
        try:
            ssh_key = str(pathlib.Path.home())+"/.ssh/id_rsa.pub"
            if not os.path.isfile(ssh_key):
                raise Exception(f"{ssh_key} does not exist!")
            #cmd = cmd
            result = subprocess.run(cmd, capture_output=True, text=True)
            print(result)
            sleep(1)
            #self.setParam('TRANSFER', 0)  # Reset trigger after successful transfer
            if result.returncode == 0:
                print("Transfer successful!")
            else:
                raise RuntimeError("Transfer not successful", result.stderr)
            return result
        except Exception as e:
            print(f"SCP transfer has failed for {cmd}!")
 
def move_hplc_files(proposal_id=proposal_id, run_id=run_id,current_cycle=current_cycle,csv=True, **kwargs):
        UV_file_prefix = str(f"{run_id}")
        remote_sample_dir = kwargs.get('current_sample')
        remote_sample_adf = "SiSa_"+f"{current_cycle}-{proposal_id}-{run_id}-"+kwargs.get('current_sample')+'.ADF'
        remote_sample_csv = f"{current_cycle}-{proposal_id}-{run_id}-"+kwargs.get('current_sample')+'.dx_DAD1E.CSV'
        UV_data = str(UV_file_prefix + "-" +remote_sample_csv)
        print(UV_data)
        remote_dir='C:/CDSProjects/HPLC/'
        remote_path = os.path.join(remote_dir, remote_sample_dir, remote_sample_adf)
        remote_path_csv = os.path.join(remote_dir, remote_sample_dir, remote_sample_csv)
        cmd = ["scp", f"xf16id@{windows_ip}:{remote_path}", f"/nsls2/data/lix/legacy/{current_cycle}/{proposal_id}/{run_id}"]
        print(f"Waiting to transfer {remote_sample_adf}....")
        result=scp_transfer(cmd)
        print(result)
        
        if csv==True:
            cmd = ["scp", f"xf16id@{windows_ip}:{remote_path_csv}", f"/nsls2/data/lix/legacy/{current_cycle}/{proposal_id}/{run_id}"]
            print(f"fetching CSV files from {remote_path_csv}")
            result=scp_transfer(cmd)
            print(result)
            
def get_UV_data(sample_name): #proxies=proxies):
    #f=requests.get(f'http://xf16id-ws4:8000/{current_cycle}-{proposal_id}-{run_id}-{sample_name}/{current_cycle}-{proposal_id}-{run_id}-{sample_name}.dx_DAD1E.CSV', proxies=proxies)
    sample_name = f"{current_cycle}-{proposal_id}-{run_id}-{sample_name}.dx_DAD1E.CSV"
    df = pd.read_csv(sample_name)
    k=df.to_numpy(dtype=float)
    #fn_h5=f"{current_sample} +.h5"
    #data=f.text
    #hdstr=dict(f.headers)
    #k=np.genfromtxt(StringIO(data), delimiter=',', dtype="float")
    
    #k=str(k).encode('ASCII')
    #df_uv = pd.read_csv(StringIO(data), sep=',', engine='python', header=None, names=['time','mAU'])
    
    
    return k #df_uv


def h5_attach_hplc(fn, fn_h5=None, grp_name=None):
    """ the hdf5 is assumed to contain a structure like this:
        LIX_104
        == hplc
        ==== data
        == primary (em, scattering patterns, ...)
        
        attach the HPLC data to the specified group
        if the group name is not give, attach to the first group in the h5 file
    """
    if fn_h5 is None:
        fn_h5 = current_sample+".h5"
        print(fn_h5)
    f = h5py.File(fn, "r+")
    if grp_name == None:
        grp_name = list(f.keys())[0]
    sample_name=list(f.keys())[0]
    k=get_UV_data(sample_name)
    # sample_name is in the file name after proposal-saf leaving out check until we verify sample name can be extracted from http server
    #and verified with sample name from HDF5 file generated.  Point is to compare what is read from server to hdf5 file already packing to make sure group name is the same.

    
    # this group is created by suitcase if using flyer-based hplc_scan
    # otherwise it has to be created first
    # it is also possible that there was a previous attempt to populate the data

    if 'hplc' in f[f"{grp_name}"].keys():
        grp = f["%s/hplc/data" % grp_name]
    else:
        grp = f.create_group(f"{grp_name}/hplc/data")
        
    key_list=list(grp.keys())
    for g in grp:
        if g in key_list:
            print("warning: %s already exists, deleting ..." % g)
            del grp[g]
    else:
        print("no UV_data previously present")
    d=np.asarray(k)
    #print(d)
    dset=grp.create_dataset('[LC Chromatogram(Detector A-Ch1)]', data=d)
    dset[:]=d
    f.close()

'''
def run_single_hplc(spreadsheet_fn, sheet_name="Samples", batchID, sample_name, exp=2, shutdown=False):
    samples, valve_position = CreateAgilentSeqFile(spreadsheet_fn, batchID, sheet_name=sheet_name)
    print("Obtaining Sample and setting PV.....")
    caput('XF:16IDC-ES{HPLC}SampleName, SampleName')
'''