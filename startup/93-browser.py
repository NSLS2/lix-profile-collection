
s = lambda hdr: f"{hdr.start['plan_name']} {hdr.start['scan_id']} ['{hdr.start['uid']:.6}']"


def f(header, factory):
    plan_name = header['start']['plan_name']
    if 'image_det' in header['start']['detectors']:
        fig = factory('Image Series')
        cs = CrossSection(fig)
        sv = StackViewer(cs, db.get_images(header, 'image'))
    elif len(header['start'].get('motors', [])) == 1:
        motor, = header['start']['motors']
        main_det, *_ = header['start']['detectors']
        fig = factory("{} vs {}".format(main_det, motor))
        ax = fig.gca()
        lp = LivePlot(main_det, motor, ax=ax)
        db.process(header, lp)


t = lambda header: "This is a {start[plan_name]}.".format(**header)


def browse():
    return BrowserWindow(db, f, t, s)
