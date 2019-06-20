## Project: Skynet V2
## Phase: N/A Road Data From Overpass
## Michael Salzarulo
## Description: Version 1.0
# Intended to be used as a command line tool. This script will convert xml files
# to csv files and contain a feature to sort the data within the file. This script is tested for use on
# open street map (osm) xml files from the overpass api.
# ----------------------------------------------------------------------------------------------------------------------
## Updates for version 1.1
# New additions to this include a query feature in which the user
# can input a bounding box in lat and long which will grab the data from overpass api.
# Additional features to be added:
#  - Find set of roads with way points and convert to csv
#  - List by road number and way points
#  - Create user defined garbage collection for extraneous way points
#  - Refined query of converted data (split roads that are divided by the bounds)
#  - Find length of the roads and add sum to csv file

import xml.etree.ElementTree as ET
import csv, os, overpy, sys


def Helpfunc(verbose=False):
    """
    This function is the help option to explain to the user how to use the program. The message can be viewed in a
    verbose form if specified by the user.

    :param verbose: Bool value defined at program run time
    :return:
    """

    if verbose:
        print("# Intended to be used as a command line tool. This script will query overpass api with a user defined \
               extent and output a csv file in the form of Road,Node,Lat,Lon.")
        print("Arguments:\n")
        print("extent(s w n e) Enter the extent of the boundary to be queried with the latitude and longitude \
        corresponding to south west north east in that order.")
    if not verbose:
        print("Input arguments:\nextent([s][w][n][e])")


def Find_mid_lat_lon(node_list):
    """
    This function will iterate over the associated nodes of each way and calculate the one dimensional mid point of
    lat and lon

    :param node_list: List of associated nodes
    :return:
    """

    min_lat = None
    max_lat = None
    min_lon = None
    max_lon = None
    for x in node_list:  # iterate ove the list and find the desired values
        if min_lat is None:
            min_lat = x.lat
        elif min_lat > x.lat:
            min_lat = x.lat

        if max_lat is None:
            max_lat = x.lat
        elif max_lat < x.lat:
            max_lat = x.lat

        if min_lon is None:
            min_lon = x.lon
        elif min_lon > x.lon:
            min_lon = x.lon

        if max_lon is None:
            max_lon = x.lon
        elif max_lon < x.lon:
            max_lon = x.lon

    midlat = ((max_lat - min_lat) / 2) + min_lat  # Mid point calculation for lat
    midlon = ((max_lon - min_lon) / 2) + min_lon  # Mid point calculation for lon

    return [midlat, midlon]


def Find_mid_points(query_result, csvobj, write=True):
    """
    This function is dependent on the find_mid_lat_long function. This is a recursive function to iterate through the
    list of query results finding the mid points of ways which encompass the road. See open street map (osm) documentation
    for further break down of nodes and ways. Found here: https://wiki.openstreetmap.org/wiki/Main_Page

    :param query_result: List of desired data to be parsed
    :param csvobj: csv File pointer
    :param write: Kwarg tells function to write to file, or not
    :return:
    """

    way = query_result[0]  # Split topmost result
    way_id = str(way.id)  # Store way id as string
    if "name" not in way.tags.keys(): way.tags["name"] = "Not named"  # Check for name tag if none is present create one
    road_name = way.tags["name"]  # Store road name
    mid_lat, mid_lon = Find_mid_lat_lon(way.nodes)  # Calculate midpoints of lat and lon
    for node in way.nodes:
        val_list = [way_id + " " + road_name, node.id, mid_lat, mid_lon]  # Store values in list with desired formatting
        if write:
            csvobj.writerow(val_list)  # Write list to csv file
        else:
            return val_list
    if len(query_result) > 1:  # Check if there are more results
        return Find_mid_points(query_result[1:], csvobj)
    else:
        return


def PrimaryQ(extent="40.0853,-75.4005,40.1186,-75.3549"):
    """
    This is the method of generating an overpass file with a user defined extent. This function will query the overpass
    api. The results of the query will be parsed and a resulting csv file will be generated.

    :param extent: User defined lat and long in the form of: south west north east
    :return:
    """

    print("Sending query to overpass ... ") # Message to user
    Qstring = """[out:xml][bbox:%s];
    (
      way[highway];
    );
    out body;
    (._;>;);
    out skel qt;""" % (extent)
    api = overpy.Overpass()  # Generate an overpass query object
    result = api.query(Qstring)  # Method to query api results in parsed data
    print("Query successful") # Message to user

    with open("Query Result.csv", "w+") as csvfp:  # Open file with handeler
        print("Generating csv file ...")  # Message to user
        header = ["Road #/id","Waypoint id (Node)", "Lat", "Lon"]  # Create header of file
        writer = csv.writer(csvfp)  # Create file writter object
        writer.writerow(header)  # Write header to file
        writer.writerow(["extent"] + extent.split()) # Write the extent to the file
        Find_mid_points(result.ways, writer)  # Recursive function to write desired data
    print("File Generated in %s" % os.getcwd())  # Message to user


def Smart_unpack(list_of_tuple):
    """
    This function will unpack a list of tuples and assign the value to the corresponding data type.

    :param list_of_tuple:
    :return unpacked_list:
    """
    unpacked_list = []
    for pair in list_of_tuple:
        if pair[0] == 'user':
            unpacked_list.append(str(pair[1]).encode('UTF-8'))
        elif pair[0] == 'lat' or pair[0] == 'lon':
            unpacked_list.append(float(pair[1]))
        elif pair[0] == 'timestamp':
            unpacked_list.append(pair[1])
        else:
            unpacked_list.append(int(pair[1]))

    return unpacked_list


def Xml2csv(path, smart=True):
    """
    This function will convert data from xml to csv. It expects a path to a directory which contains the xml files to be
    converted.

    :param path:
    :keyword smart:
    :return:
    """

    for root, _, dir in os.walk(path):  # parse folder for xml files
        files = [os.path.join(root, string) for string in dir if string[-4:] == ".xml"]  # generate list of files

    print("Selection:")  # Display to user

    # The quick and dirty method
    if not smart:  # Default method
        print("Quick and dirty")  # Display method to user
        index = 0
        for fp in files:
            with open(fp, "r") as fp:  # open file
                data = fp.read()
                data = data.split()
                ",".join(data)  # convert to csv
                with open("xml2csv_" + index + ".csv", "w+") as nfp:  # save data to new file
                    nfp.write(data)
                index + +1

    # The smart and pretty method
    else:
        print("Smart Parse")  # Display method to user
        for fp in files:
            tree = ET.parse(fp)  # Create element tree object
            root = tree.getroot()  # Get the elements of the object
            with open(fp[:-4] + ".csv", "w+") as node_data:  # Open new file for writing
                csvwriter = csv.writer(node_data)  # Generate writer object
                header = []  # Redacted
                index = 0  # Start loop index
                for node in root.findall('node'):  # Loop through all "node" elements
                    feature_data = []  # Initialize list
                    if index == 0:  # Check loop index
                        print(node.attrib.keys())
                        csvwriter.writerow(node.attrib.keys())  # Write header row
                        index += 1
                    # type conversions to match appropriate data type
                    feature_data.append(Smart_unpack(node.attrib.items()))  # unpack values
                    print(node.attrib.keys())
                    print(feature_data)
                    csvwriter.writerow(feature_data)
            # name_of_file = fp[:-4] + '.csv'  # Save name of file to string
            # print("Wrote to csv\n Generated: %s" % name_of_file)  # Display file to user
            f"Wrote to csv\n Generated: {fp[:-4] + '.csv'}"  # Display file to user

    return


def Filter_csv(path):  # This function will need to be refined based on constraints from Eric Purohit
    """
    This function will filter csv data in alphabetical order.
    :param path:
    :return:
    """
    for root, _, dir in os.walk(path):  # parse folder for csv files
        files = [os.path.join(root, string) for string in dir if dir[-4:] == ".csv"]
    for fp in files:
        with open(fp, "r") as fp:  # open csv file
            data = fp.read()
            data = data.sort()  # sort data
            print('{1}'.format(data))  # return sorted data to stdout


if __name__ == "__main__":  # The function calls in this section will be executed when this script is run from the command line
    ## Tested example for version 1.0
    # import sys
    #
    # # Add option handeling and help function here.
    #
    # print(sys.argv[1])  # Echo the file path to the user
    # Xml2csv(sys.argv[1])
    #
    # # Xml2csv("C:\\Users\\msalzarulo\\Documents\\skynetV2\\xml2csv\\")

    # Testing example for version 1.1
    # if " -h " in sys.argv or " --help " in sys.argv:
    #     if " -v " in sys.argv or " --verbose " in sys.argv:
    #         Helpfunc()
    #     else:
    #         Helpfunc(True)
    PrimaryQ("40.0810,-75.4005,40.1143,-75.3533")
