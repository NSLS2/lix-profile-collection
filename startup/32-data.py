last_scan_uid = None
last_scan_id = None

def fetch_scan(**kwargs):
    if len(kwargs) == 0:  # Retrieve last dataset
        header = db[-1]
        return header, get_table(header, fill=True)
    else:
        headers = db(**kwargs)
        return headers, get_table(headers, fill=True)
