# Scratch pad for source code

## Project: Skynet V2
## Data Generation - image mapping
## Michael Salzarulo
## Description:
# This script will scan the appropriate paths and pull the relevant files. It will use the files to create a binary
# array corresponding to the mapped coordinates of the files of interest.
# ERSI Shapefile white pages: https://www.esri.com/library/whitepapers/pdfs/shapefile.pdf

from osgeo import ogr
import gdal, os, subprocess

gdal.AllRegister()

# Need to find a better method of doing this
# Points to the directory where the mapped data of the shape files live
shp_file_path = "C:\\Users\\msalzarulo\\Documents\\skynetV2\\Pre Cyclone Idai\\Mapped_data"

# Scans the directory and saves a list of shape file paths in shape_file
for root, _, file in os.walk(shp_file_path):
    shape_file = [os.path.join(root, name) for name in file if name[-4:] == ".shp"]
    mask_file = [os.path.join(root, name) for name in file if name[-4:] == ".prj"]

# This code originates from the gdal api tutorial found at: https://gdal.org/tutorials/raster_api_tut.html
dataset = gdal.OpenEx(shape_file[0], gdal.OF_VECTOR)
# dataset = ogr.Open(shape_file[0]) # This is outdated

dataset_layer = dataset.GetLayer()
x_min, x_max, y_min, y_max = dataset_layer.GetExtent()  # This information may not used once reference projection is found

if dataset is None:
    gdal.GetLastErrorMsg()

# This method was found here : https://gis.stackexchange.com/questions/222394/how-to-convert-file-shp-to-tif-using-ogr-or-python-or-gdal
# Output_mask = gdal.OpenEx(mask_file[0], gdal.OF_VECTOR)  # This line is also busted
# Output = gdal.GetDriverByName('GTiff').Create(Output_mask, Output_mask.RasterXSize, Output_mask.RasterYSize, 1,
#                                              gdal.GDT_Byte, options=['COMPRESS=DEFLATE'])
# Output.SetProjection(Output_mask.GetProjectionRef())
# Output.SetGeoTransform(Output_mask.GetGeoTransform())

# This method was found in the ogr doumentation at : https://pcjericks.github.io/py-gdalogr-cookbook/raster_layers.html
pixel_size = 25  # huristic value.... yes I made it up
x_res = int((x_max - x_min) / pixel_size)  # set resolution on x axis
y_res = int((y_max - y_min) / pixel_size)  # set resolution on y axis

Output = gdal.GetDriverByName('GTiff').Create('ugly_mask.tif', x_res, y_res, 1, gdal.GDT_Byte) #There is an error in this line

Output.SetGeoTransform((x_min,pixel_size,0,y_max,pixel_size,0))
Band = Output.GetRasterBand(1)
Band.SetNoDataValue(0)
gdal.RasterizeLayer(Output, [1], dataset_layer, burn_values=[1])
subprocess.call("gdaladdo --config COMPRESS_OVERVIEW DEFLATE " + "mask.tif" + " 2 4 8 16 32 64", shell=True)
print("End stolen code")

# # This code was taken from https://pcjericks.github.io/py-gdalogr-cookbook/layers.html
# # I bleieve it is outdated
# def world2Pixel(geoMatrix, x, y):
#   """
#   Uses a gdal geomatrix (gdal.GetGeoTransform()) to calculate
#   the pixel location of a geospatial coordinate
#   """
#   ulX = geoMatrix[0]
#   ulY = geoMatrix[3]
#   xDist = geoMatrix[1]
#   yDist = geoMatrix[5]
#   rtnX = geoMatrix[2]
#   rtnY = geoMatrix[4]
#   pixel = int((x - ulX) / xDist)
#   line = int((ulY - y) / xDist)
#   return (pixel, line)
#
# driver = ogr.GetDriverByName("ESRI Shapefile")
# shapes = driver.Open(shape_file[0],0)
# lyr = shapes.GetLayer()
# poly=lyr.GetNextFeature()
# geom=poly.GetGeometryRef()
# pts = geom.GetGeometryRef(0)
# points = []
# pixels = []
# for p in range(pts.GetPointCount()):
#     points.append((pts.GetX(p),pts.GetY(p)))
# for p in points:
#     pixels.append(world2Pixel(geoTrans,p[0],p[1]))
print(dataset)
