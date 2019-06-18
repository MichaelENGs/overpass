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
import csv, os, overpy


def Helpfunc(verbose=False):
    if verbose:
        print("# Intended to be used as a command line tool. This script will convert xml files to csv files and contain a \
        feature to sort the data within the file. This script is tested for use on open street map (osm) xml files from \
        the overpass api.")
        print("Arguments:\n")
        print("[extent](s w n e) Enter the extent of the boundary to be queried with the latitude and longitude \
        corresponding to south west north east in that order. The extent can also be defined by name such as a town, \
        city, or country")
    if not verbose:
        print("Input arguments:\n[extent]([s][w][n][e]) | (area)")


def PrimaryQ(extent="King of Prussia"):
    Qstring = """[timeout:25][out:xml];
    (
    area[name="%s"];
    way(area)[highway][name];
    );
    out body;
    >;
    out skel qt;""" % (extent)
    api = overpy.Overpass()
    result = api.query(Qstring)
    print(result)

    # Qstring = "node(50.745,7.17,50.75,7.18);out;"
    #     # api = overpy.Overpass()
    #     # result = api.query(Qstring)
    print(len(result.nodes))


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
    Helpfunc()
    PrimaryQ()
