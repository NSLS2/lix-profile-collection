print(f"Loading {__file__}...")

def update_metadata():
    print('updating meta data ...', end='')
    RE.md['det_pos'] = ({'saxs': {'x':saxs.x.position, 'y':saxs.y.position, 'z':saxs.z.position},
                         'waxs1': {'x':waxs1.x.position, 'y':waxs1.y.position, 'z':waxs1.z.position},
                         'waxs2': {'x':waxs2.x.position, 'y':waxs2.y.position, 'z':waxs2.z.position},
                        })
    RE.md['energy'] = ({'mono_bragg': mono.bragg.position,
                        'energy': pseudoE.energy.position, 
                        'gap': pseudoE.IVUgap.position
                       })
    RE.md['optics'] = ({'wbm_y': wbm.y.position,
                        'wbm_pitch': wbm.pitch.position,
                        'dcm_y2': mono.y.position,
                        'mono_x': mono.x.position, 
                        'hfm_x1': hfm.x1.position,
                        'hfm_x2': hfm.x2.position,
                        'vfm_y1': vfm.y1.position,
                        'vfm_y2': vfm.y2.position,
                        })
    
    try:
        RE.md['CRL'] = ({'state': crl.state(), 
                         'x1': crl.x1.position,
                         'y1': crl.y1.position,
                         'x2': crl.x2.position,
                         'y2': crl.y2.position,
                         'z': crl.z.position,
                        })
    except: 
        print("crl is not defined.")    

    sdict = {}
    try:
        sdict['SSA'] = {'dx': ssa.dx.position, 'dy': ssa.dy.position}
    except:
        print("ssa is not defined.")
    sdict['DDA'] = {'x': dda.x.position, 'y': dda.y.position, 'dx': dda.dx.position, 'dy': dda.dy.position }
    sdict['Sg'] = {'x': sg2.x.position, 'y': sg2.y.position, 'dx': sg2.dx.position, 'dy': sg2.dy.position }
    RE.md['slits'] = (sdict)

    RE.md['BPM'] = ({"XBPM": xbpm.pos(),
                     "FOE": {'x': em0.x_position.get(), 'y': em0.y_position.get()},
                     "SS": {'stage position': {'x': bpm_pos.x.position, 'y': bpm_pos.y.position},
                           'beam position': {'x': bpm.x_mean.get(), 'y': bpm.y_mean.get()}},
                    })
    print('Done.')
