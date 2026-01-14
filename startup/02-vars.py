print(f"Loading {__file__}...")

from enum import Enum

class data_file_path(Enum):
    old_gpfs = '/GPFS/xf16id/exp_path'
    lustre_legacy = '/nsls2/data/lix/legacy'
    lustre_asset = '/nsls2/data/lix/asset'
    lustre_proposals = '/nsls2/data/lix/proposals'
    gpfs = '/nsls2/xf16id1/data'
    gpfs_experiments = '/nsls2/xf16id1/experiments'
    ramdisk = '/ramdisk'

#redis_host = 'xf16id-ioc2'
redis_host = 'epics-services-lix'
redis_port = 6379
current_cycle = '2026-1'
pilatus_data_dir = data_file_path.lustre_legacy.value
#pilatus_data_dir = f"{data_file_path.ramdisk.value}/hdf"
det_data_dir = pilatus_data_dir # "/home/xspress3/lix"  # 
data_destination = data_file_path.lustre_legacy.value  # this is where all IOC data files should eventually go
#proc_destination = data_file_path.lustre_proposals.value
proc_destination = data_file_path.lustre_legacy.value
procdir_prefix = "pass-"  

bl_comm_proposal = "317919"

import sys
shared_path = "/nsls2/software/mx/lix/pylibs"
sys.path = [shared_path]+sys.path

