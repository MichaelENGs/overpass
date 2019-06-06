# Scratch pad for source code

## Project: Skynet V2
## Data Generation - image mapping
## Michael Salzarulo
## Description:
# This script will scan the appropriate paths and pull the relevant files. It will use the files to create a binary
# array corresponding to the mapped coordinates of the files of interest.

import gdal, os

# Need to find a better method of doing this
# Points to the directory where the mapped data of the shape files live
shp_file_path = "C:\\Users\\msalzarulo\\Documents\\skynetV2\\Pre Cyclone Idai\\Mapped_data"

# Scans the directory and saves a list of shape file paths in shape_file
for root, _, file in os.walk(shp_file_path):
    shape_file = [os.path.join(root, name) for name in file if name[-4:] == ".shp"]

# shapes = gdal.
