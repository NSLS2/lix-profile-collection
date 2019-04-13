import glob,re

current_sample="test"

def check_sample_name(sample_name, check_for_duplicate=True):    
    if len(sample_name)>42:  # file name length limit for Pilatus detectors
        print("Error: the sample name is too long:", len(sample_name))
        return False
    l1 = re.findall('[^:._A-Za-z0-9\-]', sample_name)
    if len(l1)>0:
        print("Error: the file name contain invalid characters: ", l1)
        return False

    if check_for_duplicate:
        fl = glob.glob(data_path+sample_name+"_000*")
        if len(fl)>0:
            print("Error: files already exist for this sample name: ", sample_name)
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
        ret = check_sample_name(sample_name, exception)
        if ret==False and exception:
            raise Exception()

    current_sample = sample_name
    RE.md['sample_name'] = current_sample 
        
    return ret
    
