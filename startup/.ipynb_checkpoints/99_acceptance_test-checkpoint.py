print(f"Loading {__file__}...")

def run_acceptance_test():
    login(test_only=True)

    pil.exp_time(0.5)
    pil.set_num_images(21)
    change_sample("test1")
    RE(ct([em1, em2, pil], num=21))
    pack_h5(db[-1].uid)

    change_sample("test2")
    RE(dscan([em1, em2, pil], ss.x, -0.5, 0.5, 21))
    pack_h5(db[-1].uid)

    change_sample("test3")
    em1.averaging_time.put(0.05)
    em1.ts.averaging_time.put(0.05)
    em1.ts.num_points.put(20)
    em2.averaging_time.put(0.05)
    em2.ts.averaging_time.put(0.05)
    em2.ts.num_points.put(20)

    em1.acquire.put(1)
    em2.acquire.put(1)
    em1.ts.acquire.put(1)
    em2.ts.acquire.put(1)
    sd.monitors = [em1.ts.SumAll, em2.ts.SumAll]
    RE(raster(0.2, ss.x, -0.1, 0.1, 21, ss.y, -0.2, 0.2, 11))
    sd.monitors = []
    pack_h5(db[-1].uid)