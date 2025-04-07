print(f"Loading {__file__}...")
import json

from collections import OrderedDict
import redis

def print_scanid(name, doc):
    global last_scan_uid
    global last_scan_id

    header_attrs = ['proc_path', 'sample_name', 'plan_name']
    
    if name == 'start':
        last_scan_uid = doc['uid']
        last_scan_id = doc['scan_id']  
        print('Scan ID:', doc['scan_id'])
        print('Unique ID:', doc['uid'])
        
        hdr_dict = {"uid": doc['uid'], 
                    #"proc_path": proc_path,
                    #"sample_name": current_sample
                   }
        #pil.update_header(json.dumps(hdr_dict))
        pil.update_header(f"uid={doc['uid']}")
        
        # also update header info in Redis
        with redis.Redis(host=redis_host, port=redis_port, db=0) as r:
            hdrs = r.get('scan_info')
            if hdrs==None: # no info stored yet
                hdrs = OrderedDict({})
            else:
                hdrs = json.loads(hdrs, object_pairs_hook=OrderedDict)
                
            h = db[-1].start
            hdrs[h['uid']] = {k: h[k] for k in header_attrs}
            uids = list(hdrs.keys())
            if len(uids)>3: # keep up to 3 scans
                hdrs.popitem(last=False)
            r.set("scan_info", json.dumps(hdrs))
       
def print_scanid_stop(name, doc):
    global last_scan_uid
    global last_scan_id
    if name == 'stop':
        print('Scan ID:', last_scan_id)
        print('Unique ID:', last_scan_uid)    

def print_md(name, doc):
    if name == 'start':
        print('Metadata:\n', repr(doc))

RE.subscribe(print_scanid, 'start')
RE.subscribe(print_scanid_stop, 'stop')

# For debug purpose to see the metadata being stored
#RE.subscribe('start', print_md)


## enable live table
bec.enable_table()
#bec.disable_table()
## disable plots
#bec.enable_plots()
bec.disable_plots()

## add hints (choose from feilds given by dev.describe()), e.g: 
# ss2.y.hints = {'fields': ['ss2_y', 'ss2_y_user_setpoint']}
# em1.hints = {'fields': ['em1_current1_mean_value', 'em1_current2_mean_value']}
## or specify explicitly
#RE(relative_scan(DETS, ss2.y, -1,1, 10), LiveTable(['ss2_y', 'ss2_y_user_setpoint']))



