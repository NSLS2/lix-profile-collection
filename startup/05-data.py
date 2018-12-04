import time

global default_data_path_root
global substitute_data_path_root
global CBF_replace_data_path
global DET_replace_data_path

default_data_path_root = '/GPFS/xf16id/exp_path/'
substitute_data_path_root = '/exp_path/'
# DET_use_substitue_data_path: 
#     if true, save data into substitue path, but eventaully moved to the default path
#     the idea is that /exp_path would be the RAM disk on P1M_PPU
#     value assigned in 20-pilatus.py
# CBF_replace_data_path:
#     to let the CBF file handler know whether the files have been moved
#     value assigned in 33-CBFhandler.py

last_scan_uid = None
last_scan_id = None

def fetch_scan(**kwargs):
    if len(kwargs) == 0:  # Retrieve last dataset
        header = db[-1]
        return header, header.table(fill=True)
    else:
        headers = db(**kwargs)
        return headers, db.get_table(headers, fill=True)

def list_scans(**kwargs):
    headers = list(db(**kwargs))
    uids = []
    for h in headers:
        s = "%8s%10s%10s" % (h.start['proposal_id'], h.start['run_id'], h.start['plan_name'])
        try:
            s = "%s%8d" % (s, h.start['num_points'])
        except:
            s = "%s%8s" % (s,"")
        t = time.asctime(time.localtime(h.start['time'])).split()
        s = s + (" %s-%s-%s %s " % (t[4], t[1], t[2], t[3])) 
        try:
            s = "%s %s" % (s, h.start['sample_name'])
        except:
            pass
        print(s, h.start['uid'])
        uids.append(h.start['uid'])

    return(uids)

# map xv vlaue from range xm1=[min, max] to range xm2
def x_conv(xm1, xm2, xv):
    a = (xm2[-1]-xm2[0])/(xm1[-1]-xm1[0])
    return xm2[0]+a*(xv-xm1[0])

# example: plot_data(data, "cam04_stats1_total", "hfm_x1", "hfm_x2")
def plot_data(data, ys, xs1, xs2=None, thresh=0.8):
    yv = data[ys]
    xv1 = data[xs1]

    fig = plt.figure(figsize=(8,6))
    ax1 = fig.add_subplot(111)
    ax1.plot(xv1, yv)

    idx = yv>thresh*yv.max()
    ax1.plot(xv1[idx],yv[idx],"o")
    xp = np.average(xv1[idx], weights=yv[idx])
    xx = xv1[yv==yv.max()]
    ax1.plot([xp,xp],[yv.min(), yv.max()])
    ax1.set_xlabel(xs1)
    ax1.set_ylabel(ys)
    xm1 = [xv1[1], xv1[len(xv1)]]
    ax1.set_xlim(xm1)

    if xs2!=None:
        xv2 = data[xs2]
        ax2 = ax1.twiny()
        ax2.set_xlabel(xs2)
        #xlim1 = ax1.get_xlim()
        xm2 = [xv2[1], xv2[len(xv2)]]
        ax2.set_xlim(xm2)
        print("y max at %s=%f, %s=%f" % (xs1, xx, xs2, x_conv(xm1, xm2, xx)))
        print("y center at %s=%f, %s=%f" % (xs1, xp, xs2, x_conv(xm1, xm2, xp)))
    else:
        print("y max at %s=%f" % (xs1, xx))
        print("y center at %s=%f" % (xs1, xp))