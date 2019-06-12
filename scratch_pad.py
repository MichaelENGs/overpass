# Scratch pad for source code

## Project: Skynet V2
## Data Generation - image mapping
## Michael Salzarulo
## Description:
# This script will scan the appropriate paths and pull the relevant files. It will use the files to create a binary
# array corresponding to the mapped coordinates of the files of interest.
# ERSI Shapefile white pages: https://www.esri.com/library/whitepapers/pdfs/shapefile.pdf

from osgeo import ogr
import gdal, os, subprocess, numpy
from PIL import Image

gdal.AllRegister()

# Need to find a better method of doing this
# Points to the directory where the mapped data of the shape files live
shp_file_path = "C:\\Users\\msalzarulo\\Documents\\skynetV2\\Pre Cyclone Idai\\Mapped_data"
reference_raster = "C:\\Users\\msalzarulo\\Documents\\skynetV2\\Pre Cyclone Idai\\0023231.tif"

# Scans the directory and saves a list of shape file paths in shape_file
for root, _, file in os.walk(shp_file_path):
    shape_file = [os.path.join(root, name) for name in file if name[-4:] == ".shp"]
    mask_file = [os.path.join(root, name) for name in file if name[-4:] == ".prj"]

# This code originates from the gdal api tutorial found at: https://gdal.org/tutorials/raster_api_tut.html
dataset = gdal.OpenEx(shape_file[0], gdal.OF_VECTOR)
# check if file is open
if dataset is None:
    gdal.GetLastErrorMsg()
# check if file is open
refimage = gdal.Open(reference_raster,gdal.GA_ReadOnly)
if refimage is None:
    gdal.GetLastErrorMsg()
# dataset = ogr.Open(shape_file[0]) # This is outdated
dataset_layer = dataset.GetLayer()
x_min, x_max, y_min, y_max = dataset_layer.GetExtent()  # This information may not used once reference projection is found
# This method was found in the ogr doumentation at : https://pcjericks.github.io/py-gdalogr-cookbook/raster_layers.html
pixel_size = 25  # huristic value.... yes I made it up
x_res = int((x_max - x_min) / pixel_size)  # set resolution on x axis
if x_res == 0:
    x_res = 1 # Set to 1 for gdal create parameters
y_res = int((y_max - y_min) / pixel_size)  # set resolution on y axis
if y_res == 0:
    y_res = 1 # Set to 1 for gdal create parameters
# driver.Create(filename,xval,yval,bands,datatype) yval can not exceed 4000
Output = gdal.GetDriverByName('GTiff').Create('ugly_mask.tif', x_res, y_res, 1, gdal.GDT_Byte)
# x_res_prj = refimage.RasterXSize
# y_res_prj = refimage.RasterYSize
# Output = gdal.GetDriverByName('GTiff').Create('ugly_mask.tif', x_res_prj, y_res_prj, 1, gdal.GDT_Byte)
refimage = None # Close the tiff file
Output.SetGeoTransform((x_min,pixel_size,0,y_max,pixel_size,0))
Band = Output.GetRasterBand(1)
Band.SetNoDataValue(0)
gdal.RasterizeLayer(Output, [1], dataset_layer, burn_values=[0])
subprocess.call("gdaladdo --config COMPRESS_OVERVIEW DEFLATE " + "ugly_mask.tif" + " 2 4 8 16 32 64", shell=True)
Output.FlushCache()
print("End stolen code")
with Image.open("ugly_mask.tif") as fp:
    image_pixel_array = numpy.asarray(fp)
    # sanity check
    # if not image_pixel_array.size < 2:
    #     assert ValueError("Image mask not generated, dimensions too small")
    print(fp)
# # Note to self:
# This code will run however the resulting tif does not display as expected

with Image.open("C:\\Users\\msalzarulo\\Documents\\skynetV2\\Pre Cyclone Idai\\0023320.tif") as fp:
    myarray = numpy.asarray(fp)
    print("stop here")