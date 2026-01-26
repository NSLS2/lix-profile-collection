from bluesky.plan_stubs import open_run, close_run, stage, unstage, trigger_and_read
import pandas as pd
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A0,A1,A2,A3, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Image, PageBreak, Spacer
from reportlab.lib.units import cm

def record_pos_and_det(motors=None, detectors=None, *, md=None):
    """
    record current motor positions and detector values without moving.

    Parameters
    ----------
    motors : list, optional
        List of motor objects.
    detectors : list, optional
        List of detector.
    md : dict, 
        Metadata to include in the run.
    """
    motors = list(motors) if motors else []
    detectors = list(detectors) if detectors else []

    yield from open_run(md or {})

    # Stage detectors
    for dev in detectors:
        yield from stage(dev)

    # Trigger and read all devices (flat list)
    devices_to_read = motors + detectors
    yield from trigger_and_read(devices_to_read)

    # Unstage detectors
    for dev in reversed(detectors):
        yield from unstage(dev)

    yield from close_run()


motor_list = [wbm.y, mono.y,xbpm.x,xbpm.y,ssa.dx,ssa.dy,sg2.dx,sg2.dy,dda.dx,dda.dy]
detector_list = [bpm,em1, em2,em0]


lix_report = fast_shutter_decorator()(record_pos_and_det)


def generate_report(pdf_file="report.pdf"):
    RE(lix_report(motor_list,detector_list,md={'record':'cycle_2026_1'}))
    uids = list_scans(plan_name="record_pos_and_det")
    uida = uids[-10:]
    ht = []
    dt = []
    for i in uida:
        h,d = fetch_scan(uid=i)
        ht.append(h)
        dt.append(d)
    print("data_extracted")
    header = list(dt[0].columns)
    data_rows = []
    for i in range(10):
        block = dt[i]
        row = [block[col].iloc[1] if len(block[col]) > 1 else block[col].iloc[0] for col in header]
        data_rows.append(row)
    
    doc = SimpleDocTemplate(pdf_file,
                            pagesize=landscape(A1),
                            leftMargin=3*cm,
                            rightMargin=3*cm,
                            topMargin=3*cm,
                            bottomMargin=3*cm)
    
    elements = []
    
    chunk_size = len(motor_list+detector_list)
    page_width = landscape(A1)[0] - 4*cm
    for start in range(0, len(header), chunk_size):
        hdr_chunk = header[start:start+chunk_size]
        rows_chunk = [r[start:start+chunk_size] for r in data_rows]
        table_data = [hdr_chunk] + rows_chunk
        table = Table(table_data, colWidths=page_width/chunk_size, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.lightblue),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.25, colors.black),
            ('BOX', (0,0), (-1,-1), 1, colors.black),
            ('BACKGROUND', (0,1), (-1,-1), colors.beige)
        ]))
        elements.append(table)
        if start + chunk_size < len(header):
            elements.append(PageBreak())
    
    bpm_vals = []
    for i in range(10):
        block = dt[i]
        val = block['bpm_int_mean'].iloc[1] if len(block['bpm_int_mean']) > 1 else block['bpm_int_mean'].iloc[0]
        bpm_vals.append(val)
    
    plt.figure(figsize=(10,4))
    plt.plot(range(10), bpm_vals, marker='o')
    plt.title("bpm_int_mean")
    plt.xlabel("last 10 Historical data")
    plt.ylabel("bpm_int_mean")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig("bpm_plot_index.png")
    plt.close()
    

    elements.append(PageBreak())    # add plot to PDF
    elements.append(Spacer(1, 1*cm))
    elements.append(Image("bpm_plot_index.png", width=700, height=300))
    
    doc.build(elements) # build pdf file
    print(f"PDF with table + bpm_int_mean plot saved: {pdf_file}")