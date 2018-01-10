def updata_metadata():
    RE.md['sample_name'] = current_sample 
    RE.md['saxs'] = ({'saxs_x':saxs.x.position, 'saxs_y':saxs.y.position, 'saxs_z':saxs.z.position})
    RE.md['waxs1'] = ({'waxs1_x':waxs1.x.position, 'waxs1_y':waxs1.y.position, 'waxs1_z':waxs1.z.position})
    RE.md['waxs2'] = ({'waxs2_x':waxs2.x.position, 'waxs2_y':waxs2.y.position, 'waxs2_z':waxs2.z.position}) 
    RE.md['energy'] = ({'mono_bragg': mono.bragg.position,
                        'dcm_y2': mono.y.position,
                        'mono_x': mono.x.position,
                        'energy': getE(), 
                        'gap': get_gap()})
    RE.md['XBPM'] = XBPM_pos() 