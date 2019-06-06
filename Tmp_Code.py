# Scratch pad for source code

import gdal, os

# Need to find a better method of doing this
# Points to the directory where the mapped data of the shape files live
shp_file_path= "C:\\Users\\msalzarulo\\Documents\\skynetV2\\Pre Cyclone Idai\\Mapped_data"

# Scans the directory and saves a list of shape file paths in shape_file
for root, _, file in os.walk(shp_file_path):
    shape_file = [os.path.join(root, name) for name in file if name[-4:] == ".shp"]

#shapes = gdal.

