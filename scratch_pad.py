# Scratch pad for source code

## Project: Skynet V2
## Data Generation - image mapping
## Michael Salzarulo
## Description:
# This script will scan the appropriate paths and pull the relevant files. It will use the files to create a binary
# array corresponding to the mapped coordinates of the files of interest.

from osgeo import ogr
import gdal, os

def world2Pixel(geoMatrix, x, y):
  """
  Uses a gdal geomatrix (gdal.GetGeoTransform()) to calculate
  the pixel location of a geospatial coordinate
  """
  ulX = geoMatrix[0]
  ulY = geoMatrix[3]
  xDist = geoMatrix[1]
  yDist = geoMatrix[5]
  rtnX = geoMatrix[2]
  rtnY = geoMatrix[4]
  pixel = int((x - ulX) / xDist)
  line = int((ulY - y) / xDist)
  return (pixel, line)

# Need to find a better method of doing this
# Points to the directory where the mapped data of the shape files live
shp_file_path = "C:\\Users\\msalzarulo\\Documents\\skynetV2\\Pre Cyclone Idai\\Mapped_data"

# Scans the directory and saves a list of shape file paths in shape_file
for root, _, file in os.walk(shp_file_path):
    shape_file = [os.path.join(root, name) for name in file if name[-4:] == ".shp"]

driver = ogr.GetDriverByName("ESRI Shapefile")
shapes = driver.Open(shape_file[0],0)
lyr = shapes.GetLayer()
poly=lyr.GetNextFeature()
geom=poly.GetGeometryRef()
pts = geom.GetGeometryRef(0)
points = []
pixels = []
for p in range(pts.GetPointCount()):
    points.append((pts.GetX(p),pts.GetY(p)))
for p in points:
    pixels.append(world2Pixel(geoTrans,p[0],p[1]))
print(shapes)
