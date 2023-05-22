print(f"Loading {__file__}...")

def print_scanid(name, doc):
    global last_scan_uid
    global last_scan_id
    if name == 'start':
        last_scan_uid = doc['uid']
        last_scan_id = doc['scan_id']  
        print('Scan ID:', doc['scan_id'])
        print('Unique ID:', doc['uid'])
        pil.update_header(doc['uid'])
       
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



