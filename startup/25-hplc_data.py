def readShimadzuSection(section):
    """ the chromtographic data section starts with a header
        followed by 2-column data
        the input is a collection of strings
    """
    xdata = []
    ydata = []
    for line in section:
        tt = line.split()
        if len(tt)==2:
            try:
                x=float(tt[0])
            except ValueError:
                continue
            try:
                y=float(tt[1])
            except ValueError:
                continue
            xdata.append(x)
            ydata.append(y)
    return xdata,ydata

def writeShimadzuDatafile(fn, sections):
    """ warning: there is no error checking
        sections is a dictionary, each item correspond to a section, the key is the section name
    """
    fd = open(fn, "w+")
    for k,s in sections.items():
        fd.write(k + '\r\n' + '\r\n'.join(s) + '\r\n' + '\r\n')
    fd.close()
    
def readShimadzuDatafile(fn, chapter_num=-1, return_all_sections=False):
    """ read the ascii data from Shimadzu Lab Solutions software
        the file appear to be split in to multiple sections, each starts with [section name], 
        and ends with a empty line
        returns the data in the sections titled 
            [LC Chromatogram(Detector A-Ch1)] and [LC Chromatogram(Detector B-Ch1)]
            
        The file may be concatenated from several smaller files (chapters), resulting in sections 
        of the same name. this happens when exporting the UV/RI data. The new data seem to be 
        appended to the end of the file, and therefore can be accessed by champter# -1.
    """
    fd = open(fn, "r")
    chapters = fd.read().split('[Header]')[1:]
    fd.close()
    print(f"{fn} contains {len(chapters)} chapters, reading chapter #{chapter_num} ...")
    
    lines = ("[Header]"+chapters[chapter_num]).split('\n')
    sects = []
    while True:
        try:
            idx = lines.index('')
        except ValueError:
            break
        if idx>0:
            sects.append(lines[:idx])
        lines = lines[idx+1:]
    
    sections = {}
    for i in range(len(sects)):
        sections[sects[i][0]] = sects[i][1:]
    
    if return_all_sections:
        return sections
    
    data = {}
    header_str = '\n'.join(sections["[Header]"]) + '\n'.join(sections["[Original Files]"])
    for k in sections.keys():
        if "[LC Chromatogram" in k:
            x,y = readShimadzuSection(sections[k])
            data[k] = [x,y]
    
    return header_str,data
        
