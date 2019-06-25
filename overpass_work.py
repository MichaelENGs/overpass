## Project: Skynet V2
## Phase: N/A Road Data From Overpass
## Michael Salzarulo
## Description: Version 1.1
# Intended to be used as a command line tool. This script will automatically query the overpass api and
# return the desired data via csv file. Their is one operational filter method available to filter the output data
# with a user specified distance. The filter method will generate a new file with each pass.
# ----------------------------------------------------------------------------------------------------------------------
## Updates for version 1.2
# Features to be amended:
#  - Query function (existing module will not pass on the high side)

# Additional features to be added:
#  - Filter method 2 add nodes at user defined distance
#  - Refined query of converted data (split roads that are divided by the bounds)
#  - Find length of the roads and add sum to csv file
#  - one co-ordinate and radius bbox generation
#  - Additional tagging methods
#
# Noted issues with current version:
#  - overpy can not be used on high side implementation

import xml.etree.ElementTree as ET
import csv, os, sys, math
from urllib.request import urlopen
from urllib.error import HTTPError
from xml.sax import handler,make_parser
from decimal import Decimal
from datetime import datetime


#-----------------------------------------------------------------------------------------------------------------------
## The following is ammended from the original version found at:
# https://github.com/DinoTools/python-overpy/blob/master/overpy/__init__.py

# Try to convert some common attributes
# http://wiki.openstreetmap.org/wiki/Elements#Common_attributes
GLOBAL_ATTRIBUTE_MODIFIERS = {
    "changeset": int,
    "timestamp": lambda ts: datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"),
    "uid": int,
    "version": int,
    "visible": lambda v: v.lower() == "true"
}


class Element(object):
    """
    Base element
    """

    def __init__(self, attributes=None, result=None, tags=None):
        """
        :param attributes: Additional attributes
        :type attributes: Dict
        :param result: The result object this element belongs to
        :param tags: List of tags
        :type tags: Dict
        """

        self._result = result
        self.attributes = attributes
        attribute_modifiers = dict(GLOBAL_ATTRIBUTE_MODIFIERS.items())
        for n, m in attribute_modifiers.items():
            if n in self.attributes:
                self.attributes[n] = m(self.attributes[n])
        self.id = None
        self.tags = tags

    @classmethod
    def get_center_from_xml_dom(cls, sub_child):
        center_lat = sub_child.attrib.get("lat")
        center_lon = sub_child.attrib.get("lon")
        if center_lat is None or center_lon is None:
            raise ValueError("Unable to get lat or lon of way center.")
        center_lat = Decimal(center_lat)
        center_lon = Decimal(center_lon)
        return center_lat, center_lon

class Node(Element):
    """
    Class to represent an element of type node
    """

    _type_value = "node"

    def __init__(self, node_id=None, lat=None, lon=None, **kwargs):
        """
        :param lat: Latitude
        :type lat: Decimal or Float
        :param lon: Longitude
        :type long: Decimal or Float
        :param node_id: Id of the node element
        :type node_id: Integer
        :param kwargs: Additional arguments are passed directly to the parent class
        """

        Element.__init__(self, **kwargs)
        self.id = node_id
        self.lat = lat
        self.lon = lon

    def __repr__(self):
        return "<overpy.Node id={} lat={} lon={}>".format(self.id, self.lat, self.lon)

    @classmethod
    def from_xml(cls, child, result=None):
        """
        Create new way element from XML data
        :param child: XML node to be parsed
        :type child: xml.etree.ElementTree.Element
        :param result: The result this node belongs to
        :type result: overpy.Result
        :return: New Way oject
        :rtype: overpy.Node
        :raises overpy.exception.ElementDataWrongType: If name of the xml child node doesn't match
        :raises ValueError: If a tag doesn't have a name
        """
        if child.tag.lower() != cls._type_value:
            raise ValueError("Bad data")

        tags = {}

        for sub_child in child:
            if sub_child.tag.lower() == "tag":
                name = sub_child.attrib.get("k")
                if name is None:
                    raise ValueError("Tag without name/key.")
                value = sub_child.attrib.get("v")
                tags[name] = value

        node_id = child.attrib.get("id")
        if node_id is not None:
            node_id = int(node_id)
        lat = child.attrib.get("lat")
        if lat is not None:
            lat = Decimal(lat)
        lon = child.attrib.get("lon")
        if lon is not None:
            lon = Decimal(lon)

        attributes = {}
        ignore = ["id", "lat", "lon"]
        for n, v in child.attrib.items():
            if n in ignore:
                continue
            attributes[n] = v

        return cls(node_id=node_id, lat=lat, lon=lon, tags=tags, attributes=attributes, result=result)

class Way(Element):
    """
    Class to represent an element of type way
    """

    _type_value = "way"

    def __init__(self, way_id=None, center_lat=None, center_lon=None, node_ids=None, **kwargs):
        """
        :param node_ids: List of node IDs
        :type node_ids: List or Tuple
        :param way_id: Id of the way element
        :type way_id: Integer
        :param kwargs: Additional arguments are passed directly to the parent class
        """

        Element.__init__(self, **kwargs)
        #: The id of the way
        self.id = way_id

        #: List of Ids of the associated nodes
        self._node_ids = node_ids

        #: The lat/lon of the center of the way (optional depending on query)
        self.center_lat = center_lat
        self.center_lon = center_lon

    def __repr__(self):
        return "<overpy.Way id={} nodes={}>".format(self.id, self._node_ids)

    @property
    def nodes(self):
        """
        List of nodes associated with the way.
        """
        return self.get_nodes()

    def get_nodes(self, resolve_missing=False):
        """
        Get the nodes defining the geometry of the way
        :param resolve_missing: Try to resolve missing nodes.
        :type resolve_missing: Boolean
        :return: List of nodes
        :rtype: List of overpy.Node
        :raises overpy.exception.DataIncomplete: At least one referenced node is not available in the result cache.
        :raises overpy.exception.DataIncomplete: If resolve_missing is True and at least one node can't be resolved.
        """
        result = []
        resolved = False

        for node_id in self._node_ids:
            try:
                node = self._result.get_node(node_id)
            except:
                node = None

            if node is not None:
                result.append(node)
                continue

            if not resolve_missing:
                raise ValueError("Bad data")

            # We tried to resolve the data but some nodes are still missing
            if resolved:
                raise ValueError("Bad data")

            query = ("\n"
                     "[out:json];\n"
                     "way({way_id});\n"
                     "node(w);\n"
                     "out body;\n"
                     )
            query = query.format(
                way_id=self.id
            )
            tmp_result = self._result.api.query(query)
            self._result.expand(tmp_result)
            resolved = True

            try:
                node = self._result.get_node(node_id)
            except:
                node = None

            if node is None:
                raise ValueError("Bad data")

            result.append(node)

        return result

    @classmethod
    def from_xml(cls, child, result=None):
        """
        Create new way element from XML data
        :param child: XML node to be parsed
        :type child: xml.etree.ElementTree.Element
        :param result: The result this node belongs to
        :type result: overpy.Result
        :return: New Way oject
        :rtype: overpy.Way
        :raises overpy.exception.ElementDataWrongType: If name of the xml child node doesn't match
        :raises ValueError: If the ref attribute of the xml node is not provided
        :raises ValueError: If a tag doesn't have a name
        """
        if child.tag.lower() != cls._type_value:
            raise EnvironmentError("it's busted")

        tags = {}
        node_ids = []
        center_lat = None
        center_lon = None

        for sub_child in child:
            if sub_child.tag.lower() == "tag":
                name = sub_child.attrib.get("k")
                if name is None:
                    raise ValueError("Tag without name/key.")
                value = sub_child.attrib.get("v")
                tags[name] = value
            if sub_child.tag.lower() == "nd":
                ref_id = sub_child.attrib.get("ref")
                if ref_id is None:
                    raise ValueError("Unable to find required ref value.")
                ref_id = int(ref_id)
                node_ids.append(ref_id)
            if sub_child.tag.lower() == "center":
                (center_lat, center_lon) = cls.get_center_from_xml_dom(sub_child=sub_child)

        way_id = child.attrib.get("id")
        if way_id is not None:
            way_id = int(way_id)

        attributes = {}
        ignore = ["id"]
        for n, v in child.attrib.items():
            if n in ignore:
                continue
            attributes[n] = v

        return cls(way_id=way_id, center_lat=center_lat, center_lon=center_lon,
                   attributes=attributes, node_ids=node_ids, tags=tags, result=result)

class Relation(Element):
    """
    Class to represent an element of type relation
    """

    _type_value = "relation"

    def __init__(self, rel_id=None, center_lat=None, center_lon=None, members=None, **kwargs):
        """
        :param members:
        :param rel_id: Id of the relation element
        :type rel_id: Integer
        :param kwargs:
        :return:
        """

        Element.__init__(self, **kwargs)
        self.id = rel_id
        self.members = members

        #: The lat/lon of the center of the way (optional depending on query)
        self.center_lat = center_lat
        self.center_lon = center_lon

    def __repr__(self):
        return "<overpy.Relation id={}>".format(self.id)

    @classmethod
    def from_xml(cls, child, result=None):
        """
        Create new way element from XML data
        :param child: XML node to be parsed
        :type child: xml.etree.ElementTree.Element
        :param result: The result this node belongs to
        :type result: overpy.Result
        :return: New Way oject
        :rtype: overpy.Relation
        :raises overpy.exception.ElementDataWrongType: If name of the xml child node doesn't match
        :raises ValueError: If a tag doesn't have a name
        """
        if child.tag.lower() != cls._type_value:
            raise EnvironmentError("it's busted")

        tags = {}
        members = []
        center_lat = None
        center_lon = None

        supported_members = [RelationNode, RelationWay, RelationRelation, RelationArea]
        for sub_child in child:
            if sub_child.tag.lower() == "tag":
                name = sub_child.attrib.get("k")
                if name is None:
                    raise ValueError("Tag without name/key.")
                value = sub_child.attrib.get("v")
                tags[name] = value
            if sub_child.tag.lower() == "member":
                type_value = sub_child.attrib.get("type")
                for member_cls in supported_members:
                    if member_cls._type_value == type_value:
                        members.append(
                            member_cls.from_xml(
                                sub_child,
                                result=result
                            )
                        )
            if sub_child.tag.lower() == "center":
                (center_lat, center_lon) = cls.get_center_from_xml_dom(sub_child=sub_child)

        rel_id = child.attrib.get("id")
        if rel_id is not None:
            rel_id = int(rel_id)

        attributes = {}
        ignore = ["id"]
        for n, v in child.attrib.items():
            if n in ignore:
                continue
            attributes[n] = v

        return cls(
            rel_id=rel_id,
            attributes=attributes,
            center_lat=center_lat,
            center_lon=center_lon,
            members=members,
            tags=tags,
            result=result
        )

class Area(Element):
    """
    Class to represent an element of type area
    """

    _type_value = "area"

    def __init__(self, area_id=None, **kwargs):
        """
        :param area_id: Id of the area element
        :type area_id: Integer
        :param kwargs: Additional arguments are passed directly to the parent class
        """

        Element.__init__(self, **kwargs)
        #: The id of the way
        self.id = area_id

    def __repr__(self):
        return "<overpy.Area id={}>".format(self.id)

    @classmethod
    def from_xml(cls, child, result=None):
        """
        Create new way element from XML data
        :param child: XML node to be parsed
        :type child: xml.etree.ElementTree.Element
        :param result: The result this node belongs to
        :type result: overpy.Result
        :return: New Way oject
        :rtype: overpy.Way
        :raises overpy.exception.ElementDataWrongType: If name of the xml child node doesn't match
        :raises ValueError: If the ref attribute of the xml node is not provided
        :raises ValueError: If a tag doesn't have a name
        """
        if child.tag.lower() != cls._type_value:
            raise ValueError("bad data")

        tags = {}

        for sub_child in child:
            if sub_child.tag.lower() == "tag":
                name = sub_child.attrib.get("k")
                if name is None:
                    raise ValueError("Tag without name/key.")
                value = sub_child.attrib.get("v")
                tags[name] = value

        area_id = child.attrib.get("id")
        if area_id is not None:
            area_id = int(area_id)

        attributes = {}
        ignore = ["id"]
        for n, v in child.attrib.items():
            if n in ignore:
                continue
            attributes[n] = v

        return cls(area_id=area_id, attributes=attributes, tags=tags, result=result)


class RelationMember(object):
    """
    Base class to represent a member of a relation.
    """

    def __init__(self, attributes=None, geometry=None, ref=None, role=None, result=None):
        """
        :param ref: Reference Id
        :type ref: Integer
        :param role: The role of the relation member
        :type role: String
        :param result:
        """
        self.ref = ref
        self._result = result
        self.role = role
        self.attributes = attributes
        self.geometry = geometry

    @classmethod
    def from_xml(cls, child, result=None):
        """
        Create new RelationMember from XML data
        :param child: XML node to be parsed
        :type child: xml.etree.ElementTree.Element
        :param result: The result this element belongs to
        :type result: overpy.Result
        :return: New relation member oject
        :rtype: overpy.RelationMember
        :raises overpy.exception.ElementDataWrongType: If name of the xml child node doesn't match
        """
        if child.attrib.get("type") != cls._type_value:
            raise EnvironmentError("it's busted")

        ref = child.attrib.get("ref")
        if ref is not None:
            ref = int(ref)
        role = child.attrib.get("role")

        attributes = {}
        ignore = ["geometry", "ref", "role", "type"]
        for n, v in child.attrib.items():
            if n in ignore:
                continue
            attributes[n] = v

        geometry = None
        for sub_child in child:
            if sub_child.tag.lower() == "nd":
                if geometry is None:
                    geometry = []
                geometry.append(
                    RelationWayGeometryValue(
                        lat=Decimal(sub_child.attrib["lat"]),
                        lon=Decimal(sub_child.attrib["lon"])
                    )
                )

        return cls(
            attributes=attributes,
            geometry=geometry,
            ref=ref,
            role=role,
            result=result
        )

class RelationNode(RelationMember):
    _type_value = "node"

    def resolve(self, resolve_missing=False):
        return self._result.get_node(self.ref, resolve_missing=resolve_missing)

    def __repr__(self):
        return "<overpy.RelationNode ref={} role={}>".format(self.ref, self.role)

class RelationWay(RelationMember):
    _type_value = "way"

    def resolve(self, resolve_missing=False):
        return self._result.get_way(self.ref, resolve_missing=resolve_missing)

    def __repr__(self):
        return "<overpy.RelationWay ref={} role={}>".format(self.ref, self.role)


class RelationWayGeometryValue(object):
    def __init__(self, lat, lon):
        self.lat = lat
        self.lon = lon

    def __repr__(self):
        return "<overpy.RelationWayGeometryValue lat={} lon={}>".format(self.lat, self.lon)

class RelationRelation(RelationMember):
    _type_value = "relation"

    def resolve(self, resolve_missing=False):
        return self._result.get_relation(self.ref, resolve_missing=resolve_missing)

    def __repr__(self):
        return "<overpy.RelationRelation ref={} role={}>".format(self.ref, self.role)

class RelationArea(RelationMember):
    _type_value = "area"

    def resolve(self, resolve_missing=False):
        return self._result.get_area(self.ref, resolve_missing=resolve_missing)

    def __repr__(self):
        return "<overpy.RelationArea ref={} role={}>".format(self.ref, self.role)


class OSMSAXHandler(handler.ContentHandler):
    """
    SAX parser for Overpass XML response.
    """
    #: Tuple of opening elements to ignore
    ignore_start = ('osm', 'meta', 'note', 'bounds', 'remark')
    #: Tuple of closing elements to ignore
    ignore_end = ('osm', 'meta', 'note', 'bounds', 'remark', 'tag', 'nd', 'center')

    def __init__(self, result):
        """
        :param result: Append results to this result set.
        :type result: overpy.Result
        """
        handler.ContentHandler.__init__(self)
        self._result = result
        self._curr = {}
        #: Current relation member object
        self.cur_relation_member = None

    def startElement(self, name, attrs):
        """
        Handle opening elements.
        :param name: Name of the element
        :type name: String
        :param attrs: Attributes of the element
        :type attrs: Dict
        """
        if name in self.ignore_start:
            return
        try:
            handler = getattr(self, '_handle_start_%s' % name)
        except AttributeError:
            raise KeyError("Unknown element start '%s'" % name)
        handler(attrs)

    def endElement(self, name):
        """
        Handle closing elements
        :param name: Name of the element
        :type name: String
        """
        if name in self.ignore_end:
            return
        try:
            handler = getattr(self, '_handle_end_%s' % name)
        except AttributeError:
            raise KeyError("Unknown element end '%s'" % name)
        handler()

    def _handle_start_center(self, attrs):
        """
        Handle opening center element
        :param attrs: Attributes of the element
        :type attrs: Dict
        """
        center_lat = attrs.get("lat")
        center_lon = attrs.get("lon")
        if center_lat is None or center_lon is None:
            raise ValueError("Unable to get lat or lon of way center.")
        self._curr["center_lat"] = Decimal(center_lat)
        self._curr["center_lon"] = Decimal(center_lon)

    def _handle_start_tag(self, attrs):
        """
        Handle opening tag element
        :param attrs: Attributes of the element
        :type attrs: Dict
        """
        try:
            tag_key = attrs['k']
        except KeyError:
            raise ValueError("Tag without name/key.")
        self._curr['tags'][tag_key] = attrs.get('v')

    def _handle_start_node(self, attrs):
        """
        Handle opening node element
        :param attrs: Attributes of the element
        :type attrs: Dict
        """
        self._curr = {
            'attributes': dict(attrs),
            'lat': None,
            'lon': None,
            'node_id': None,
            'tags': {}
        }
        if attrs.get('id', None) is not None:
            self._curr['node_id'] = int(attrs['id'])
            del self._curr['attributes']['id']
        if attrs.get('lat', None) is not None:
            self._curr['lat'] = Decimal(attrs['lat'])
            del self._curr['attributes']['lat']
        if attrs.get('lon', None) is not None:
            self._curr['lon'] = Decimal(attrs['lon'])
            del self._curr['attributes']['lon']

    def _handle_end_node(self):
        """
        Handle closing node element
        """
        self._result.append(Node(result=self._result, **self._curr))
        self._curr = {}

    def _handle_start_way(self, attrs):
        """
        Handle opening way element
        :param attrs: Attributes of the element
        :type attrs: Dict
        """
        self._curr = {
            'center_lat': None,
            'center_lon': None,
            'attributes': dict(attrs),
            'node_ids': [],
            'tags': {},
            'way_id': None
        }
        if attrs.get('id', None) is not None:
            self._curr['way_id'] = int(attrs['id'])
            del self._curr['attributes']['id']

    def _handle_end_way(self):
        """
        Handle closing way element
        """
        self._result.append(Way(result=self._result, **self._curr))
        self._curr = {}

    def _handle_start_area(self, attrs):
        """
        Handle opening area element
        :param attrs: Attributes of the element
        :type attrs: Dict
        """
        self._curr = {
            'attributes': dict(attrs),
            'tags': {},
            'area_id': None
        }
        if attrs.get('id', None) is not None:
            self._curr['area_id'] = int(attrs['id'])
            del self._curr['attributes']['id']

    def _handle_end_area(self):
        """
        Handle closing area element
        """
        self._result.append(Area(result=self._result, **self._curr))
        self._curr = {}

    def _handle_start_nd(self, attrs):
        """
        Handle opening nd element
        :param attrs: Attributes of the element
        :type attrs: Dict
        """
        if isinstance(self.cur_relation_member, RelationWay):
            if self.cur_relation_member.geometry is None:
                self.cur_relation_member.geometry = []
            self.cur_relation_member.geometry.append(
                RelationWayGeometryValue(
                    lat=Decimal(attrs["lat"]),
                    lon=Decimal(attrs["lon"])
                )
            )
        else:
            try:
                node_ref = attrs['ref']
            except KeyError:
                raise ValueError("Unable to find required ref value.")
            self._curr['node_ids'].append(int(node_ref))

    def _handle_start_relation(self, attrs):
        """
        Handle opening relation element
        :param attrs: Attributes of the element
        :type attrs: Dict
        """
        self._curr = {
            'attributes': dict(attrs),
            'members': [],
            'rel_id': None,
            'tags': {}
        }
        if attrs.get('id', None) is not None:
            self._curr['rel_id'] = int(attrs['id'])
            del self._curr['attributes']['id']

    def _handle_end_relation(self):
        """
        Handle closing relation element
        """
        self._result.append(Relation(result=self._result, **self._curr))
        self._curr = {}

    def _handle_start_member(self, attrs):
        """
        Handle opening member element
        :param attrs: Attributes of the element
        :type attrs: Dict
        """

        params = {
            'attributes': {},
            'ref': None,
            'result': self._result,
            'role': None
        }
        if attrs.get('ref', None):
            params['ref'] = int(attrs['ref'])
        if attrs.get('role', None):
            params['role'] = attrs['role']

        cls_map = {
            "area": RelationArea,
            "node": RelationNode,
            "relation": RelationRelation,
            "way": RelationWay
        }
        cls = cls_map.get(attrs["type"])
        if cls is None:
            raise ValueError("Undefined type for member: '%s'" % attrs['type'])

        self.cur_relation_member = cls(**params)
        self._curr['members'].append(self.cur_relation_member)

    def _handle_end_member(self):
        self.cur_relation_member = None


# End ammended module
# ----------------------------------------------------------------------------------------------------------------------

class Salzarulo_overpass_query(object):

    def __init__(self,read_chunk_size=4096, url=None):
        self.url=url
        if url is None:
            url = input("Please select alternate url to query")
            self.url = url
        self.read_chunck_size = read_chunk_size

    def query(self,query):
        if not isinstance(query,bytes):
            query = query.encode("utf-8")
        try:
            f = urlopen(self.url,query)
        except HTTPError as e:
            f = e
        response = f.read(self.read_chunck_size)
        while True:
            data = f.read(self.read_chunck_size)
            if len(data) == 0:
                break
            response = response + data
        f.close()
        if f.code >= 200:
            e = "Query error"


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


def Header_write(header, csvobj):
    """
    This function will write the metadata information to the csv file header.

    :param header: List containing meta data and header data
    :param csvobj: Object to write to.
    :return:
    """

    for row in header:
        csvobj.writerow(row)


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
        val_list = [way_id + " " + road_name, node.id, node.lat, node.lon]  # Store values in list with desired formatting
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

    print("Sending query to overpass ... ")  # Message to user

    Qstring = """[out:xml][bbox:%s];
    (
      way[highway];
    );
    out body;
    (._;>;);
    out skel qt;""" % (extent)
    api = overpy.Overpass()  # Generate an overpass query object
    result = api.query(Qstring)  # Method to query api results in parsed data

    print("Query successful")  # Message to user

    with open("Query Result.csv", "w+") as csvfp:  # Open file with handeler
        print("Generating csv file ...")  # Message to user
        header = ["Road #/id", "Waypoint id (Node)", "Lat", "Lon"]  # Create header of file
        writer = csv.writer(csvfp)  # Create file writter object
        meta_data = [["extent"] + extent.split(), header]  # Store meta data as list
        Header_write(meta_data, writer)  # Write meta data to file
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


def Calculate_distance(coords_set1, coords_set2):
    """
    This function expects two sets of co-ordinates. It will use the Haversine formula to calculate the distance
    between the two points.

    :param prev_coords:
    :param cur_coords:
    :return:
    """

    radius_of_earth = 6371  # mean value in km from: https://www.movable-type.co.uk/scripts/latlong.html
    # Unpack co-ordinate sets
    previous_lat, previous_lon = coords_set1
    current_lat, current_lon = coords_set2
    # Haversine formula
    square_of_chord = math.sin(abs(current_lat - previous_lat) / 2) ** 2 + \
                      math.cos(current_lat) * \
                      math.cos(previous_lat) * \
                      math.sin(abs(current_lon - previous_lon) / 2) ** 2
    angular_distance = 2 * math.atan2(math.sqrt(square_of_chord), math.sqrt(1 - square_of_chord))
    distance_between_points = radius_of_earth * angular_distance
    return distance_between_points


def Calculate_coordinates(start_set,distance):
    radius_of_earth = 6371  # mean value in km from: https://www.movable-type.co.uk/scripts/latlong.html
    end_set="foo"
    # square of chord= 
    angular_distance = distance/radius_of_earth
    return end_set


def Filter_csv(version=1, min_distance=None):
    """
    This function expects no input parameters however they can be defined by the user. Two versions of this function
    are available version 1 will execute by default.
    Version 1:
    A new csv file will be created in which the nodes that are less than the minimum distance will be removed from the
    original query results.
    Version 2:
    A new csv file will be created in which a node will be generated at the minimum distance from the previous node.

    :param version: Int specifying which filter to be run defaults to version 1
    :param min_distance: Int must be defined at runtime: distance in km
    :return:
    """

    # User data entry sanity check
    assert type(version) == int, "version must be an integer either 1 or 2"
    assert version == 2 or version == 1, "version must be either 1 or 2"

    print("Beginning filter process %d:" % version)  # Message to user
    if min_distance is None:  # Check if minimum distance is defined
        min_distance = input("Please specify minimum distance")  # Prompt user for entry

    with open("Query Result.csv", "r", newline='') as Master_List:  # Open csv file from original query
        with open("Filtered Results version_%d.csv" % version, "w+") as Child_List:  # Create or truncate csv file to write
            Master_Read = csv.reader(Master_List)  # Create read object
            Child_Write = csv.writer(Child_List)  # Create write object

            previous_coordinates = 0
            count = 0
            meta_data = []
            for mdata in Master_Read:
                if mdata == []:  # Check if anthing was read
                    continue  # Skip loop

                # Read meta data and write to new file
                if "count" in dir():  # Check if count is defined
                    if count < 2:  # Check value of count
                        if count == 1:
                            mdata.append("Distance from last point")  # Append new column to header
                        assert mdata is not None,"Broken master file data"  # Sanity check writing None type to file will result in error
                        meta_data.append(mdata)  # Add meta data to list
                        count += 1  # Incriment counter
                        continue  # Skip rest of loop
                    if count == 2 and count < 4:
                        Header_write(meta_data, Child_Write)  # Write meta data to file
                        previous_meta = mdata[:-2]
                        previous_coordinates = [math.radians(float(x)) for x in
                                                mdata[-2:]]  # Unpack and convert lat and lon
                        del count  # Delete count
                        continue  # Skip rest of loop

                current_coordinates = [math.radians(float(x)) for x in mdata[-2:]]  # Unpack and convert lat and lon
                # Same node check
                if previous_coordinates == current_coordinates: # Check for duplicate co-ordinates
                    if mdata[1] != previous_meta[-1]: # Check for separate node ids
                        raise IOError("Duplicate lat and lon for different nodes, This is an overpass error")
                    else:
                        continue # Skip rest of loop

                if version == 1:  # Check version number
                    # Initialize data values
                    distance = Calculate_distance(previous_coordinates,
                                                  current_coordinates)  # Call distance calculation function
                    pretty_list = [x for x in mdata]  # Copy list values
                    pretty_list.append(distance)  # Append to list
                    if distance > min_distance:  # Check if calculated distance exceeds minimum distance
                        Child_Write.writerow(pretty_list)  # Write data to csv file in pretty format
                        previous_meta = mdata[:-2] # Save meta data
                        previous_coordinates = current_coordinates  # Set values for next loop
                    previous_loop = pretty_list # Save values for next loop

                if version == 2:
                    print("hello world")
                    # coordinates = Calculate_coordinates(start,distance)
            #End main loop

            if previous_loop[1] != previous_meta[1]: # Check if last values are not written to file
                Child_Write.writerow(pretty_list) # Write to file
            return


if __name__ == "__main__":  # The function calls in this section will be executed when this script is run from the command line
    import overpy # Only available for testing

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
    Filter_csv(min_distance=0)