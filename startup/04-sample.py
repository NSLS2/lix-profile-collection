import glob,re

current_sample="test"

def check_sample_name(sample_name):    
    if len(sample_name)>42:  # file name length limit for Pilatus detectors
        print("Error: the sample name is too long:", len(sample_name))
        return False
    l1 = re.findall('[^:._A-Za-z0-9\-]', sample_name)
    if len(l1)>0:
        print("Error: the file name contain invalid characters: ", l1)
        return False

    if data_path is None:
        change_path()
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
        ret = check_sample_name(sample_name)
        if ret==False and exception:
            raise Exception()

    current_sample = sample_name
    RE.md['sample_name'] = current_sample 
        
    return ret
    
    
import pandas
import numpy as np

def parseSpreadsheet(infilename, sheet_name=0):
    excel_data = pandas.read_excel(infilename, header=1)
    DataFrame = pandas.read_excel(infilename, sheet_name=sheet_name)
    return DataFrame.to_dict()


def get_samples(spreadSheet, holderName, check_sname=True):
    d = parseSpreadsheet(spreadSheet)

    sl = list(d['sampleName'].values())
    for ss in sl:
        if sl.count(ss)>1:
            raise Exception('duplicate sample name: %s' % ss)
    
    if holderName is None:
        hidx = [i for i in range(len(d['holderName']))]
    else:
        hidx = [i for i in range(len(d['holderName'])) if d['holderName'][i]==holderName]
    samples = {}
        
    for i in hidx:
        sample = {}
        sampleName = d['sampleName'][i]
        if check_sname:
            if not check_sample_name(sampleName):
                raise Exception("change sample name: %s, files already exist." % sampleName)
        sample['position'] = d['position'][i]
        if 'bufferName' not in d.keys():
            samples[sampleName] = sample
            continue
        elif d['bufferName'][i] is not np.nan:
            sample['bufferName'] = d['bufferName'][i]
            samples[sampleName] = sample

    for k,s in samples.items():
        # make sure that the buffer exists and is in the same row as the sample
        if 'bufferName' not in s.keys():
            continue
        if s['bufferName'] not in samples.keys():
            raise Exception('buffer does not exist: %s .' % s['bufferName'])
        if (s['position']-samples[s['bufferName']]['position']) %2 == 1:
            raise Exception('sample and buffer are not in the same row: %s, %s .' % (k, s['bufferName']) )
    
    return samples

