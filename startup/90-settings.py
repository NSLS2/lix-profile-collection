
def print_scanid(name, doc):
    global last_scan_uid
    global last_scan_id
    if name == 'start':
        last_scan_uid = doc['uid']
        last_scan_id = doc['scan_id']  
        print('Scan ID:', doc['scan_id'])
        print('Unique ID:', doc['uid'])
        for d in set(pilatus_detectors_ext+pilatus_detectors) & set(gs.DETS):
            d.HeaderString.put("uid=%s" % doc['uid'])
       
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
