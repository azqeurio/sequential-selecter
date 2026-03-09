import xml.etree.ElementTree as ET
from pathlib import Path

def parse_xmp_preset(xmp_path: Path | str) -> dict:
    """
    Parses an Adobe Lightroom .xmp preset file and maps its CRS values 
    to our internal color engine parameters.
    
    Returns a dictionary of mapped parameters. Returns empty dict on failure.
    """
    params = {}
    try:
        tree = ET.parse(str(xmp_path))
        root = tree.getroot()
        
        # XMP namespaces are usually defined like:
        # xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
        # We can just search the text or use generic ns finding.
        
        # A simple robust way to parse is iter() over all elements and check tags/attributes.
        crs_prefix = "{http://ns.adobe.com/camera-raw-settings/1.0/}"
        
        for elem in root.iter():
            # Sometimes values are stored as attributes on the main Description node
            if 'Description' in elem.tag:
                # Iterate attributes
                for key, val in elem.attrib.items():
                    if 'Exposure2012' in key:
                        # usually in EV shifts, e.g. +0.5
                        params['exposure'] = float(val) * 20 # map to our -100 to 100 scale roughly
                    elif 'Contrast2012' in key:
                        params['contrast'] = float(val)
                    elif 'Highlights2012' in key:
                        params['highlights'] = float(val)
                    elif 'Shadows2012' in key:
                        params['shadows'] = float(val)
                    elif 'Whites2012' in key:
                        params['whites'] = float(val)
                    elif 'Blacks2012' in key:
                        params['blacks'] = float(val)
                    elif 'Clarity2012' in key:
                        # Map clarity to contrast loosely if we only have contrast
                        pass 
                    elif 'Vibrance' in key:
                        params['saturation'] = float(val) # Approximation
                    elif 'Saturation' in key and 'Sat' not in key:
                        # HueSat adjustments are complex, just basic saturation
                        params['saturation'] = float(val)
                    elif 'Temperature' in key:
                        params['temperature'] = float(val) / 50.0 # Normalize 2000-50000K to -100, 100
                    elif 'Tint' in key:
                        params['tint'] = float(val)
            
            # Sometimes they are child elements
            if crs_prefix in elem.tag:
                tag_name = elem.tag.replace(crs_prefix, '')
                val = elem.text
                if val is None:
                    continue
                    
                if tag_name == 'Exposure2012':
                    params['exposure'] = float(val) * 20
                elif tag_name == 'Contrast2012':
                    params['contrast'] = float(val)
                elif tag_name == 'Highlights2012':
                    params['highlights'] = float(val)
                elif tag_name == 'Shadows2012':
                    params['shadows'] = float(val)
                elif tag_name == 'Whites2012':
                    params['whites'] = float(val)
                elif tag_name == 'Blacks2012':
                    params['blacks'] = float(val)
                elif tag_name == 'Vibrance':
                    params['saturation'] = float(val)
                elif tag_name == 'Temperature':
                    params['temperature'] = float(val) / 50.0
                elif tag_name == 'Tint':
                    params['tint'] = float(val)
                    
    except Exception as e:
        print(f"Failed to parse XMP {xmp_path}: {e}")
        
    # Clamp all mapped values to our -100 to 100 range
    for k, v in params.items():
        params[k] = max(-100, min(100, int(v)))
        
    return params
