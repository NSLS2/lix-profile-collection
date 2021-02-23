import glob,re
from enum import Enum

#global default_data_path_root
#global substitute_data_path_root

class data_file_path(Enum):
    old_gpfs = '/GPFS/xf16id/exp_path'
    gpfs = '/nsls2/xf16id1/data'
    ramdisk = '/exp_path'

current_sample="test"

def check_sample_name(sample_name, sub_dir=None, check_for_duplicate=True, check_dir=False):    
    if len(sample_name)>42:  # file name length limit for Pilatus detectors
        print("Error: the sample name is too long:", len(sample_name))
        return False
    l1 = re.findall('[^:._A-Za-z0-9\-]', sample_name)
    if len(l1)>0:
        print("Error: the file name contain invalid characters: ", l1)
        return False

    if check_for_duplicate:
        f_path = data_path
        if sub_dir is not None:
            f_path += ('/'+sub_dir+'/')
        #if DET_replace_data_path:
            #f_path = data_path.replace(default_data_path_root, substitute_data_path_root)
        if PilatusFilePlugin.froot == data_file_path.ramdisk:
            f_path = data_path.replace(data_file_path.gpfs.value, data_file_path.ramdisk.value)
        if check_dir:
            fl = glob.glob(f_path+sample_name)
        else:
            fl = glob.glob(f_path+sample_name+"_000*")
        if len(fl)>0:
            print(f"Error: name already exists: {sample_name} at {f_path}")
            return False

    return True
    
def change_sample(sample_name=None, check_sname=True, exception=True):
    """ use sample_name=None to avoid checking the sample name
        this method could be used in other functions that call change_sample(), 
        e.g. for solution scattering data collection
    """
    global current_sample
    
    if data_path is None:
        change_path()
    
    ret = True
    if sample_name is None or sample_name == "":
        sample_name = "test"
    elif check_sname:
        ret = check_sample_name(sample_name) #, exception)
        if ret==False and exception:
            raise Exception()

    current_sample = sample_name
    RE.md['sample_name'] = current_sample 
        
    return ret
    
