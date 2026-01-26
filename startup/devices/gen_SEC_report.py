import os, tempfile, re, subprocess, copy
import nbformat
from nbformat import validate
import lixtools
from py4xs.utils import run
import time
import numpy as np
import pandas as pd
global proc_path

def gen_SEC_report(fn, exp_fn, atsas_path=""):
    """Create an HTML report summarizing static solution scattering data in the specified h5 file."""
    dn = os.path.dirname(fn) or "."
    dn = os.path.abspath(dn)

    bn_parts = os.path.basename(fn).split(".")
    if bn_parts[-1] != "h5":
        raise Exception(f"{bn_parts} does not appear to be a h5 file.")
    bn = bn_parts[0]

    tmp_dir = tempfile.gettempdir()

    # Adjust this to wherever your template really lives.
    fn0 = os.path.abspath("/nsls2/data/lix/shared/config/bluesky/profile_collection/startup/devices/hplc_processing-SEC_template.ipynb")

    fn1 = os.path.join(dn, f"{bn}_report.ipynb")
    executed_ipynb = os.path.join(tmp_dir, f"{bn}_executed.ipynb")
    out_html_name = f"{bn}_report.html"
    out_html_tmp = os.path.join(tmp_dir, out_html_name)
    out_html_final = os.path.join(dn, out_html_name)

    print("preparing the notebook ...")

    nb = nbformat.read(fn0, as_version=4)

  
    for cell in nb.cells:
        src = cell.get("source", "")
        if isinstance(src, str):
            src = src.replace("00template00.h5", fn)
            src = src.replace("00exp00.h5" , exp_fn)
            cell["source"] = src



    validate(nb)
    nbformat.write(nb, fn1)


    with open(fn1, "rb") as f:
        first = f.read(3)
    if first == b"\xef\xbb\xbf":

        with open(fn1, "rb") as f:
            data = f.read()
        with open(fn1, "wb") as f:
            f.write(data[3:])

    print("executing ...")

    # Forcing this environment as nbconvert does not work in standard pixi environment in jupyter lab (bad json config files
    py = "/nsls2/conda/envs/2024-3.0-py311-tiled/bin/python"
    share = "/nsls2/conda/envs/2024-3.0-py311-tiled/share/jupyter"

   
    cmd_exec = (
        f'JUPYTER_PATH="{share}" '
        f'"{py}" -m jupyter nbconvert "{fn1}" '
        f'--to notebook '
        f'--ExecutePreprocessor.enabled=True '
        f'--ExecutePreprocessor.timeout=600 '
        f'--output "{os.path.basename(executed_ipynb)}" '
        f'--output-dir "{tmp_dir}"'
    )
    ret = run(["bash", "-lc", cmd_exec], debug=True)

    cmd_html = (
        f'JUPYTER_PATH="{share}" '
        f'"{py}" -m jupyter nbconvert "{executed_ipynb}" '
        f'--to html '
        f'--template lab '
        f'--TemplateExporter.exclude_input=True '
        f'--output "{out_html_name}" '
        f'--output-dir "{tmp_dir}"'
    )
    ret = run(["bash", "-lc", cmd_html], debug=True)

    print("cleaning up ...")
    
    ret = run(["mv", out_html_tmp, out_html_final], debug=True)

  
    ret = run(["rm", "-f", fn1, executed_ipynb], debug=True)

    print("done:", out_html_final)
    return out_html_final


