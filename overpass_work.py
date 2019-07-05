## Project: Skynet V2
## Phase: N/A Road Data From Overpass
## Michael Salzarulo
## Description: Version 1.4
# Intended to be used as a command line tool. This script will automatically query the overpass api and
# return the desired data via csv file. This software comes equip with an interface to swiftly guide the user through
# process of generating and analyzing data.
# ----------------------------------------------------------------------------------------------------------------------


import xml.etree.ElementTree as ET
import csv, os, sys, math, re
from urllib.request import urlopen
from urllib.error import HTTPError
from xml.sax import handler, make_parser
from decimal import Decimal
from datetime import datetime
from collections import OrderedDict

sys.setrecursionlimit(2000)  # Heuristic value
# -----------------------------------------------------------------------------------------------------------------------
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

XML_PARSER_DOM = 1
XML_PARSER_SAX = 2


def is_valid_type(element, cls):
    """
    Test if an element is of a given type.
    :param Element() element: The element instance to test
    :param Element cls: The element class to test
    :return: False or True
    :rtype: Boolean
    """
    return isinstance(element, cls) and element.id is not None


class Result(object):
    """
    Class to handle the result.
    """

    def __init__(self, elements=None, api=None):
        """
        :param List elements:
        :param api:
        :type api: overpy.Overpass
        """
        if elements is None:
            elements = []
        self._areas = OrderedDict((element.id, element) for element in elements if is_valid_type(element, Area))
        self._nodes = OrderedDict((element.id, element) for element in elements if is_valid_type(element, Node))
        self._ways = OrderedDict((element.id, element) for element in elements if is_valid_type(element, Way))
        self._relations = OrderedDict((element.id, element)
                                      for element in elements if is_valid_type(element, Relation))
        self._class_collection_map = {Node: self._nodes, Way: self._ways, Relation: self._relations, Area: self._areas}
        self.api = api

    def expand(self, other):
        """
        Add all elements from an other result to the list of elements of this result object.
        It is used by the auto resolve feature.
        :param other: Expand the result with the elements from this result.
        :type other: overpy.Result
        :raises ValueError: If provided parameter is not instance of :class:`overpy.Result`
        """
        if not isinstance(other, Result):
            raise ValueError("Provided argument has to be instance of overpy:Result()")

        other_collection_map = {Node: other.nodes, Way: other.ways, Relation: other.relations, Area: other.areas}
        for element_type, own_collection in self._class_collection_map.items():
            for element in other_collection_map[element_type]:
                if is_valid_type(element, element_type) and element.id not in own_collection:
                    own_collection[element.id] = element

    def append(self, element):
        """
        Append a new element to the result.
        :param element: The element to append
        :type element: overpy.Element
        """
        if is_valid_type(element, Element):
            self._class_collection_map[element.__class__].setdefault(element.id, element)

    def get_elements(self, filter_cls, elem_id=None):
        """
        Get a list of elements from the result and filter the element type by a class.
        :param filter_cls:
        :param elem_id: ID of the object
        :type elem_id: Integer
        :return: List of available elements
        :rtype: List
        """
        result = []
        if elem_id is not None:
            try:
                result = [self._class_collection_map[filter_cls][elem_id]]
            except KeyError:
                result = []
        else:
            for e in self._class_collection_map[filter_cls].values():
                result.append(e)
        return result

    def get_ids(self, filter_cls):
        """
        :param filter_cls:
        :return:
        """
        return list(self._class_collection_map[filter_cls].keys())

    def get_node_ids(self):
        return self.get_ids(filter_cls=Node)

    def get_way_ids(self):
        return self.get_ids(filter_cls=Way)

    def get_relation_ids(self):
        return self.get_ids(filter_cls=Relation)

    def get_area_ids(self):
        return self.get_ids(filter_cls=Area)

    @classmethod
    def from_xml(cls, data, api=None, parser=None):
        """
        Create a new instance and load data from xml data or object.

        .. note::
            If parser is set to None, the functions tries to find the best parse.
            By default the SAX parser is chosen if a string is provided as data.
            The parser is set to DOM if an xml.etree.ElementTree.Element is provided as data value.
        :param data: Root element
        :type data: str | xml.etree.ElementTree.Element
        :param api: The instance to query additional information if required.
        :type api: Overpass
        :param parser: Specify the parser to use(DOM or SAX)(Default: None = autodetect, defaults to SAX)
        :type parser: Integer | None
        :return: New instance of Result object
        :rtype: Result
        """
        if parser is None:
            if isinstance(data, str):
                parser = XML_PARSER_SAX
            else:
                parser = XML_PARSER_DOM

        result = cls(api=api)
        if parser == XML_PARSER_DOM:
            import xml.etree.ElementTree as ET
            if isinstance(data, str):
                root = ET.fromstring(data)
            elif isinstance(data, ET.Element):
                root = data
            else:
                raise ValueError("Bad data")

            for elem_cls in [Node, Way, Relation, Area]:
                for child in root:
                    if child.tag.lower() == elem_cls._type_value:
                        result.append(elem_cls.from_xml(child, result=result))

        elif parser == XML_PARSER_SAX:
            from io import StringIO
            source = StringIO(data)
            sax_handler = OSMSAXHandler(result)
            parser = make_parser()
            parser.setContentHandler(sax_handler)
            parser.parse(source)
        else:
            raise Exception("Unknown XML parser")
        return result

    def get_area(self, area_id, resolve_missing=False):
        """
        Get an area by its ID.
        :param area_id: The area ID
        :type area_id: Integer
        :param resolve_missing: Query the Overpass API if the area is missing in the result set.
        :return: The area
        :rtype: overpy.Area
        :raises overpy.exception.DataIncomplete: The requested way is not available in the result cache.
        :raises overpy.exception.DataIncomplete: If resolve_missing is True and the area can't be resolved.
        """
        areas = self.get_areas(area_id=area_id)
        if len(areas) == 0:
            if resolve_missing is False:
                raise ValueError("Bad data")

            query = ("\n"
                     "[out:json];\n"
                     "area({area_id});\n"
                     "out body;\n"
                     )
            query = query.format(
                area_id=area_id
            )
            tmp_result = self.api.query(query)
            self.expand(tmp_result)

            areas = self.get_areas(area_id=area_id)

        if len(areas) == 0:
            raise ValueError("Bad data")

        return areas[0]

    def get_areas(self, area_id=None, **kwargs):
        """
        Alias for get_elements() but filter the result by Area
        :param area_id: The Id of the area
        :type area_id: Integer
        :return: List of elements
        """
        return self.get_elements(Area, elem_id=area_id, **kwargs)

    def get_node(self, node_id, resolve_missing=False):
        """
        Get a node by its ID.
        :param node_id: The node ID
        :type node_id: Integer
        :param resolve_missing: Query the Overpass API if the node is missing in the result set.
        :return: The node
        :rtype: overpy.Node
        :raises overpy.exception.DataIncomplete: At least one referenced node is not available in the result cache.
        :raises overpy.exception.DataIncomplete: If resolve_missing is True and at least one node can't be resolved.
        """
        nodes = self.get_nodes(node_id=node_id)
        if len(nodes) == 0:
            if not resolve_missing:
                raise ValueError("Bad data")

            query = ("\n"
                     "[out:json];\n"
                     "node({node_id});\n"
                     "out body;\n"
                     )
            query = query.format(
                node_id=node_id
            )
            tmp_result = self.api.query(query)
            self.expand(tmp_result)

            nodes = self.get_nodes(node_id=node_id)

        if len(nodes) == 0:
            raise ValueError("Bad data")

        return nodes[0]

    def get_nodes(self, node_id=None, **kwargs):
        """
        Alias for get_elements() but filter the result by Node()
        :param node_id: The Id of the node
        :type node_id: Integer
        :return: List of elements
        """
        return self.get_elements(Node, elem_id=node_id, **kwargs)

    def get_relation(self, rel_id, resolve_missing=False):
        """
        Get a relation by its ID.
        :param rel_id: The relation ID
        :type rel_id: Integer
        :param resolve_missing: Query the Overpass API if the relation is missing in the result set.
        :return: The relation
        :rtype: overpy.Relation
        :raises overpy.exception.DataIncomplete: The requested relation is not available in the result cache.
        :raises overpy.exception.DataIncomplete: If resolve_missing is True and the relation can't be resolved.
        """
        relations = self.get_relations(rel_id=rel_id)
        if len(relations) == 0:
            if resolve_missing is False:
                raise ValueError("Bad data")

            query = ("\n"
                     "[out:json];\n"
                     "relation({relation_id});\n"
                     "out body;\n"
                     )
            query = query.format(
                relation_id=rel_id
            )
            tmp_result = self.api.query(query)
            self.expand(tmp_result)

            relations = self.get_relations(rel_id=rel_id)

        if len(relations) == 0:
            raise ValueError("Bad data")

        return relations[0]

    def get_relations(self, rel_id=None, **kwargs):
        """
        Alias for get_elements() but filter the result by Relation
        :param rel_id: Id of the relation
        :type rel_id: Integer
        :return: List of elements
        """
        return self.get_elements(Relation, elem_id=rel_id, **kwargs)

    def get_way(self, way_id, resolve_missing=False):
        """
        Get a way by its ID.
        :param way_id: The way ID
        :type way_id: Integer
        :param resolve_missing: Query the Overpass API if the way is missing in the result set.
        :return: The way
        :rtype: overpy.Way
        :raises overpy.exception.DataIncomplete: The requested way is not available in the result cache.
        :raises overpy.exception.DataIncomplete: If resolve_missing is True and the way can't be resolved.
        """
        ways = self.get_ways(way_id=way_id)
        if len(ways) == 0:
            if resolve_missing is False:
                raise ValueError("Bad data")

            query = ("\n"
                     "[out:json];\n"
                     "way({way_id});\n"
                     "out body;\n"
                     )
            query = query.format(
                way_id=way_id
            )
            tmp_result = self.api.query(query)
            self.expand(tmp_result)

            ways = self.get_ways(way_id=way_id)

        if len(ways) == 0:
            raise ValueError("Bad data")

        return ways[0]

    def get_ways(self, way_id=None, **kwargs):
        """
        Alias for get_elements() but filter the result by Way
        :param way_id: The Id of the way
        :type way_id: Integer
        :return: List of elements
        """
        return self.get_elements(Way, elem_id=way_id, **kwargs)

    area_ids = property(get_area_ids)
    areas = property(get_areas)
    node_ids = property(get_node_ids)
    nodes = property(get_nodes)
    relation_ids = property(get_relation_ids)
    relations = property(get_relations)
    way_ids = property(get_way_ids)
    ways = property(get_ways)


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

class Salzarulo_Overpass_Query(object):
    """
    Class to access the overpass api

    """

    default_url = "http://overpass-api.de/api/interpreter"

    def __init__(self, read_chunk_size=4096, url=None):
        self.url = self.default_url
        if url is not None:
            # url = input("Please select alternate url to query")
            self.url = url
        self.read_chunck_size = read_chunk_size

    def query(self, query):
        if not isinstance(query, bytes):
            query = query.encode("utf-8")
        try:
            f = urlopen(self.url, query)
        except HTTPError as e:
            f = e
        response = f.read(self.read_chunck_size)
        while True:
            data = f.read(self.read_chunck_size)
            if len(data) == 0:
                break
            response = response + data
        f.close()
        if f.code > 200:
            e = "Query error"
        else:
            content_type = f.getheader("Content-Type")
            with open("Query result.xml", "w+") as fp:
                fp.write(response.decode("utf-8"))
            return self.parse_xml(response)

    def parse_xml(self, data, encoding="utf-8", parser=XML_PARSER_SAX):
        """
        :param data: Raw XML Data
        :type data: String or Bytes
        :param encoding: Encoding to decode byte string
        :type encoding: String
        :return: Result object
        :rtype: overpy.Result
        """
        if parser is None:
            parser = self.xml_parser

        if isinstance(data, bytes):
            data = data.decode(encoding)

        m = re.compile("<remark>(?P<msg>[^<>]*)</remark>").search(data)
        if m:
            self._handle_remark_msg(m.group("msg"))

        return Result.from_xml(data, api=self, parser=parser)


def Helpfunc(verbose=False):
    """
    This function is the help option to explain to the user how to use the program. The message can be viewed in a
    verbose form if specified by the user.

    :param verbose: Bool value defined at program run time
    :return:
    """

    if verbose:
        message = """
        This script is a command line tool that will query overpass api with a user defined extent and output a csv file in the form of Road,Node,Lat,Lon. It can then filter the data and preform analysis on the data.\n\n
        overpass_work.py query 40.0853,-75.4005,40.1186,-75.3549                 Initialize an overpass api query
        overpass_work.py filter_version 2 distance .05                           Filter the data from the initial overpass api query and accept a user specified distance
        overpass_work.py cell 40.08 -75.4 40.09 -75.38                           Run the refined query and analyze data inside defined cell 
        overpass_work.py cell 40.08 -75.4 40.09 -75.38 cell 50 -76 51 -76.5      Generate a list of cells to be analyzed\n\n
        The filter and cell methods of this tool expect that a query to the overpass api has already been made and stored.
        Future iteration of this tool will allow for cells to be read through csv files.
        """
        print(message)
        verbose = False
    if not verbose:
        message = """
        overpass_work.py [options] {co-ordinates: (min lat)(min lon)(max lat)(max lon)}
        supported options:
        -h or --help                 Display help message '--help' method will display example program calls
        query {co-ordinates}         This will trigger a query of the overpass api and save the results
        filter_version {distance}    Filter the results of the query optionally specify a minimum distance in kilometers where the default is 0
        cell {co-ordinates|file}     Trigger a refined analysis of the original query with in the specified plane. Additionally multiple cells 
                                     can be defined with a single execution. Alternatively a file containing multiple cell co-ordinates can be
                                     specified at run time.
        """
        print(message)


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
    # mid_lat, mid_lon = Find_mid_lat_lon(way.nodes)  # Calculate midpoints of lat and lon
    for node in way.nodes:
        val_list = [way_id + " " + road_name, node.id, node.lat,
                    node.lon]  # Store values in list with desired formatting
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
    api = Salzarulo_Overpass_Query()  # Generate an overpass query object
    result = api.query(Qstring)  # Method to query api results in parsed data
    print("Query successful")  # Message to user

    with open("Query Result.csv", "w+", newline="") as csvfp:  # Open file with handeler
        print("Generating csv file ...")  # Message to user
        header = ["Road #/id", "Waypoint id (Node)", "Lat", "Lon"]  # Create header of file
        writer = csv.writer(csvfp)  # Create file writter object
        meta_data = [["extent"] + extent.split(), header]  # Store meta data as list
        # Header_write(meta_data[1], writer)  # Write meta data to file
        writer.writerow(header)
        Find_mid_points(result.ways, writer)  # Recursive function to write desired data
    print("File Generated in %s" % os.getcwd())  # Message to user


def SecondQ(cell_list):
    """
    Refined query, this function will break down the data into user defined cells and generate two output files.
    A file with a comprehensive list of the cells their ids and the corresponding ways along with the corresponding
    nodes.
    A file with a list of the cells their ids and the road densities per cell.

    :param cell_list:
    :return:
    """

    more_loops = True
    with open("Cell separated data.csv", "w+", newline="") as nfp:
        writer = csv.writer(nfp)
        cell_id = 0  # initialize cell id
        node_id = 0  # initialize node id
        previous_node = None
        previous_way = None
        previous_coordinates = None
        previous_lon = None
        previous_lat = None
        for cell in cell_list:  # loop cell by cell
            if isinstance(cell_list, str):
                cell = cell_list
                more_loops = False
            road_length = 0
            total_road_length = 0
            cell_data = cell + "_" + str(cell_id)
            # open data

            with open("Filtered results version_2.csv", "r") as fp:
                reader = csv.reader(fp)
                # read data
                for data in reader:
                    #print(data)
                    if data == []:
                        continue
                    # Create and write header
                    if "Road #/id" in data:
                        # print("here")
                        pretty_list = [x for x in data]
                        pretty_list.insert(0, "cell id/bbox")
                        writer.writerow(pretty_list)
                        continue

                    # organize data
                    way, node, lat, lon = data
                    current_coordinates = [float(lat), float(lon)]
                    row_to_write = [cell_data, way, node, lat, lon]
                    if Isincell(current_coordinates, cell):
                        writer.writerow(row_to_write)
                        if way == previous_way:
                            road_length = Calculate_distance(previous_coordinates, current_coordinates)

                    # Check to see way crosses cell boundary
                    if way == previous_way and \
                            previous_coordinates != current_coordinates and \
                            (Isincell(previous_coordinates, cell) or Isincell(current_coordinates, cell)):
                        boundary_coordinates = Generate_boundary_coordinates(previous_coordinates, current_coordinates,
                                                                             cell)
                        node = "Generated node # %d" % node_id
                        node_id += 1
                        lat, lon = boundary_coordinates
                        row_to_write = [cell_data, way, node, lat, lon]
                        writer.writerow(row_to_write)
                        road_length = Calculate_distance(previous_coordinates, boundary_coordinates)

                    # set data for next loop
                    previous_way, previous_node, previous_lat, previous_lon = data
                    previous_coordinates = [float(previous_lat), float(previous_lon)]

                    # Calculate road densities
                    total_road_length += road_length
            with open("Road density analysis.csv", "a", newline="") as nnfp:
                cell_writer = csv.writer(nnfp)
                row_to_write = [cell_data, "total road length(km): %f" % total_road_length]
                cell_writer.writerow(row_to_write)
            cell_id += 1  # Increment cell id
            if not more_loops:
                return


def Isincell(node, cell):
    """
    This function will organize the data in the cell and return a boolean value based on in the point falls in the cell.

    :param node:
    :param cell:
    :return:
    """

    lat_list, lon_list = Cell_data_strip(cell)

    lat_node = Decimal(node[0])
    lon_node = Decimal(node[1])
    min_lat = min(lat_list)
    min_lon = min(lon_list)
    max_lat = max(lat_list)
    max_lon = max(lon_list)
    # check lat value in bounds
    if lat_node > min_lat and lat_node < max_lat and lon_node > min_lon and lon_node < max_lon:
        return True
    return False


def Generate_boundary_coordinates(previous_coordinates, current_coordinates, cell):
    """
    This function will generate coordinates of a point that lies on the boundary of the given cell using the law of
    similar right triangles.

    :param previous_coordinates:
    :param current_coordinates:
    :param cell:
    :return:
    """

    distance = Calculate_distance(previous_coordinates, current_coordinates)  # Calculate distance between points

    # Unpack data
    cell_lat_list, cell_lon_list = Cell_data_strip(cell)
    previous_lat, previous_lon = [float(x) for x in previous_coordinates]
    lat, lon = [float(x) for x in current_coordinates]

    # Calculate direction agnostic values
    north_south = abs(previous_lon - lon)
    east_west = abs(previous_lat - lat)
    point_to_point_cartesian_displacement = east_west  # Default value assumes current point outside cell
    short_lat = min(map(lambda x: abs(lat - x), cell_lat_list))  # Displacement to boundary
    if previous_lon > max(cell_lon_list) or previous_lon < min(cell_lon_list):  # Check if lon vale outside cell
        point_to_point_cartesian_displacement = north_south
        short_lon = min(map(lambda x: abs(lon - x), cell_lon_list))
    if Isincell(current_coordinates, cell):  # Check if current point in cell
        point_to_point_cartesian_displacement = east_west
        short_lon = min(map(lambda x: abs(lat - x), cell_lon_list))
        if lon > max(cell_lon_list) or lon < min(cell_lon_list):  # Check lon outside cell
            point_to_point_cartesian_displacement = north_south
            short_lon = min(map(lambda x: abs(lon - x), cell_lon_list))
    ratio = point_to_point_cartesian_displacement / distance
    if ratio > 1:
        ratio = 1 - ratio
    theta = math.acos(ratio)  # Calculate angle

    short_x = float(short_lat)  # Default assume lat is edge of interest
    if point_to_point_cartesian_displacement == north_south:  # Check position of point
        short_x = (short_lon)
    short_distance = short_x / math.cos(theta)  # Calculate distance to boundary line
    coordinates = Calculate_coordinates(previous_coordinates, current_coordinates,
                                        short_distance)  # Calculate co-ordinates of boundary point
    return coordinates


def Cell_data_strip(cell):
    """
    Convert cell parameters to usable data.

    :param cell:
    :return:
    """

    # Convert data to usable format
    cell_num = [float(x) for x in cell.split()]
    lat_list = []
    lon_list = []
    # Generate list of lat and lon
    for x in range(len(cell_num)):
        if x % 2 == 0:
            lat_list.append(cell_num[x])
        else:
            lon_list.append(cell_num[x])

    return [lat_list, lon_list]


def Calculate_distance(coords_set1, coords_set2):
    """
    This function expects two sets of co-ordinates. It will use the Haversine formula to calculate the distance
    between the two points. Returns the distance in Kilometers

    :param prev_coords:
    :param cur_coords:
    :return:
    """

    radius_of_earth = 6371  # mean value in km from: https://www.movable-type.co.uk/scripts/latlong.html
    # Unpack co-ordinate sets
    previous_lat, previous_lon = [float(x) for x in coords_set1]
    current_lat, current_lon = [float(x) for x in coords_set2]
    # Haversine formula
    square_of_chord = math.sin(abs(current_lat - previous_lat) / 2) ** 2 + \
                      math.cos(current_lat) * \
                      math.cos(previous_lat) * \
                      math.sin(abs(current_lon - previous_lon) / 2) ** 2
    angular_distance = 2 * math.atan2(math.sqrt(square_of_chord), math.sqrt(1 - square_of_chord))
    distance_between_points = abs(radius_of_earth * angular_distance)
    return distance_between_points


def Calculate_coordinates(start_set, end_set, distance):
    lat_start, lon_start = [math.degrees(x) for x in start_set]
    lat_end, lon_end = [math.degrees(x) for x in end_set]
    x = float(abs(lat_start - lat_end))
    y = float(abs(lon_start - lon_end))
    mag = math.sqrt(abs((x ** 2) - (y ** 2)))
    if mag == 0:
        return [lon_start, lon_start]
    if x == 0 and y != 0:
        mag = math.sqrt((y ** 2))
        unit_vector = (y / mag)
        lat_point = float(lat_start)
        lon_point = float(lon_start) + distance * unit_vector
        coordinate_set = [lat_point, lon_point]
        return coordinate_set
    if y == 0 and x != 0:
        mag = math.sqrt((x ** 2))
        unit_vector = (x / mag)
        lat_point = float(lat_start) + distance * unit_vector
        lon_point = float(lon_start)
        coordinate_set = [lat_point, lon_point]
        return coordinate_set
    if x == 0 and y == 0:
        return [lat_start, lon_start]
    unit_vector = (x / mag, y / mag)
    lat_point = float(lat_start) + distance * unit_vector[0]
    lon_point = float(lon_start) + distance * unit_vector[1]
    coordinate_set = [lat_point, lon_point]
    return coordinate_set


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
        min_distance = float(input("Please specify minimum distance"))  # Prompt user for entry

    with open("Query Result.csv", "r", newline='') as Master_List:  # Open csv file from original query
        with open("Filtered Results version_%d.csv" % version, "w+",
                  newline="") as Child_List:  # Create or truncate csv file to write
            Master_Read = csv.reader(Master_List)  # Create read object
            Child_Write = csv.writer(Child_List)  # Create write object

            previous_coordinates = 0
            count = 1
            meta_data = []
            previous_loop = [0, 0, 0, 0]
            for mdata in Master_Read:
                if mdata == []:  # Check if anthing was read
                    continue  # Skip loop

                # Read meta data and write to new file
                if "count" in dir():  # Check if count is defined
                    if count < 2:  # Check value of count
                        if count == 1:
                            if version == 1:
                                mdata.append("Distance from last point (km)")  # Append new column to header
                            if version == 2:
                                generated_node_count = 0
                        assert mdata is not None, "Broken query data"  # Sanity check writing None type to file will result in error
                        meta_data.append(mdata)  # Add meta data to list
                        count += 1  # Incriment counter
                        continue  # Skip rest of loop
                    if count == 2:
                        Header_write(meta_data, Child_Write)  # Write meta data to file
                        previous_loop = [x for x in mdata]  # Unpack data for first iteration
                        del count  # Delete count
                        continue  # Skip rest of loop

                # Organize data
                current_coordinates = [math.radians(float(x)) for x in mdata[-2:]]  # Unpack and convert lat and lon
                previous_coordinates = [math.radians(float(x)) for x in previous_loop[2:4]]
                current_way = mdata[0]
                previous_way = previous_loop[0]
                current_node = mdata[1]
                previous_node = previous_loop[1]
                distance = Calculate_distance(previous_coordinates,
                                              current_coordinates)  # Call distance calculation function
                pretty_list = [x for x in mdata]  # Copy list values

                # Same node check
                if previous_coordinates == current_coordinates:  # Check for duplicate co-ordinates
                    if current_node != previous_node and "Generated" not in previous_node:  # Check for separate node ids
                        raise IOError("Duplicate lat and lon for different nodes, This is an overpass error")
                    else:
                        continue  # Skip rest of loop

                # Begin filter process
                if current_way == previous_way:  # Check for same road
                    if version == 1:  # Check version number
                        # Initialize data values
                        pretty_list.append(distance)  # Append to list
                        if distance > min_distance:  # Check if calculated distance exceeds minimum distance
                            previous_coordinates = current_coordinates  # Set values for next loop
                            Child_Write.writerow(pretty_list)  # Write data to csv file in pretty format
                            saved_node = pretty_list[1]

                    # Higher priority
                    if version == 2:  # Check version number
                        if distance > min_distance:  # Check if points exceed min distance
                            pretty_list_generated = [x for x in pretty_list]
                            coordinates = Calculate_coordinates(previous_coordinates, current_coordinates, min_distance)
                            node_str = "Generated node # %d" % generated_node_count  # save string to write
                            generated_node_count += 1  # incriment generated id
                            pretty_list_generated[1] = node_str
                            pretty_list_generated[-2], pretty_list_generated[-1] = coordinates
                            Child_Write.writerow(pretty_list_generated)
                        Child_Write.writerow(pretty_list)  # Write data to csv file in pretty format
                        saved_node = pretty_list[1]
                        previous_coordinates = [math.degrees(x) for x in previous_coordinates]
                        if previous_coordinates == coordinates:
                            pretty_list[-2:] = [math.degrees(x) for x in current_coordinates]
                else:
                    if saved_node != previous_node:
                        Child_Write.writerow([previous_way, previous_node, *previous_coordinates])
                    Child_Write.writerow(pretty_list)

                previous_loop = pretty_list  # Save values for next loop
            # End main loop

            print("Filter process complete.")
            return


def Generate_cell_list(cell_file=None,csvobj=None,cell_list=[],reader=None,length_of_reader=None):
    """
    This function will support the generation of a cell list via the input file.

    :param cell_file:
    :param csvobj:
    :param cell_list:
    :param reader:
    :param length_of_reader:
    :return:
    """

    if csvobj is None:
        fp = open(cell_file,"r")
        reader = csv.reader(fp)
        length_of_reader = sum(1 for row in reader)
        fp.close()
        del reader
        fp = open(cell_file, "r")
        reader = csv.reader(fp)
    for data in reader:
        if data == []:
            continue
        formatted_data = " ".join(data)
        cell_list.append(formatted_data)
        index_in_reader = reader.line_num + 1
        if length_of_reader - index_in_reader > 0:
            return Generate_cell_list(cell_list, reader[1:])
    fp.close()
    del reader
    return cell_list

#TODO: add method to be accepted by command line input
def Present():


    # open query meta data and sort
    # I need extent of query
    # I need cell of query
    # generate 4 corners from extent
    # with open("analysis_meta.txt","r") as fp:
    #     meta_data = fp.read()
    #     for data in meta_data:
    #         extent = data

    # generate bbox kml file
    bbox = """
<?xml version="1.0" encoding="UTF-8"?>

<!--UNCLASSIFIED-->
<kml xmlns="http://www.opengis.net/kml/2.2">
	<Placemark>
	<Style id="bbox">
	  <LineStyle>
		<width>5</width>
		<altitudeMode>relativeToSeaFloor</altitudeMode>
		<color>ff000000</color>
		<color>normal</color>
	  </LineStyle>
	 </Style>
	  <name>Bounding Box</name>
	  <LookAt>
		<longitude>-75.4005</longitude>
		<latitude>40.853</latitude>
		<tilt>0</tilt>
		<range>6800</range>
		<altitudeMode>relativeToSeaFloor</altitudeMode>
	  </LookAt>
	  <LineString>
	  <styleUrl>#bbox</styleUrl>
		<extrude>1</extrude>
		<coordinates>
		
		
		  %s
		
		
		</coordinates>
	  </LineString>
	  <description><![CDATA[<table border=1 cellpadding=2 cellspacing=0><tr><td colspan=2><b>Emphasis</b></td></tr><tr><td nowrap>Collection Request Name:</td><td nowrap>CTAR_Any_EO</td></tr><tr><td nowrap>Target Name:</td><td nowrap>customaoi</td></tr><tr><td nowrap>Sensor ID:</td><td nowrap>11</td></tr><tr><td nowrap>Rev:</td><td nowrap>107438</td></tr><tr><td nowrap>Pass:</td><td nowrap>7</td></tr><tr><td nowrap>TCA:</td><td nowrap>06/25/2019 15:33:51 Z</td></tr><tr><td nowrap>Predicted Time To Collect [s] [min - max (mid)]:</td><td nowrap>1 - 1 (1)</td></tr></table><br><table border=1 cellpadding=2 cellspacing=0><tr><td colspan=2><b>Collection Request</b></td></tr><tr><td nowrap>Name</td><td nowrap>CTAR_Any_EO</td></tr><tr><td nowrap>Justification</td><td nowrap>This is a test</td></tr><tr><td nowrap>Sensor Type</td><td nowrap>PAN</td></tr><tr><td nowrap>Target Type</td><td nowrap>DSA</td></tr><tr><td nowrap>Collection Type</td><td nowrap>ADHOC</td></tr><tr><td nowrap>Supplier Preference</td><td nowrap>FALSE</td></tr><tr><td nowrap>CollectionPeriod</td><td nowrap>1.0 DAYS</td></tr><tr><td nowrap>Start Date</td><td nowrap>06/25/2019 00:00:00 Z</td></tr><tr><td nowrap>Stop Date</td><td nowrap>06/25/2019 00:00:00 Z</td></tr><tr><td nowrap>Earliest Imaging Time</td><td nowrap>00:00:00</td></tr><tr><td nowrap>Latest Imaging Time</td><td nowrap>23:59:59</td></tr><tr><td nowrap>Weather Threshold</td><td nowrap>20.0</td></tr><tr><td nowrap>Required NIIRS</td><td nowrap>0.0</td></tr><tr><td nowrap>Desired NIIRS</td><td nowrap>0.0</td></tr><tr><td nowrap>Min Graze Angle / Target El [deg]</td><td nowrap>30.0</td></tr><tr><td nowrap>Max Graze Angle / Target El [deg]</td><td nowrap>90.0</td></tr><tr><td nowrap>Min Azimuth Angle [deg]</td><td nowrap>0.0</td></tr><tr><td nowrap>Max Azimuth Angle [deg]</td><td nowrap>360.0</td></tr><tr><td nowrap>Min Sun Elevation Angle [deg]</td><td nowrap>-4.0</td></tr><tr><td nowrap>Max Sun Elevation Angle [deg]</td><td nowrap>90.0</td></tr><tr><td nowrap>Min Sun Azimuth Angle [deg]</td><td nowrap>0.0</td></tr><tr><td nowrap>Max Sun Azimuth Angle [deg]</td><td nowrap>360.0</td></tr></table>]]></description>
	</Placemark>
</kml>
<!--UNCLASSIFIED-->
    """ % bounding_box_coordinates
    with open("bbox.kml", "w+") as fp:
        fp.write(bbox)
    # generate cell kml file
    header = """
<?xml version="1.0" encoding="UTF-8"?>

<!--UNCLASSIFIED-->
<kml xmlns="http://www.opengis.net/kml/2.2">
	<Placemark>
		 <Style id="cell">
	  <LineStyle>
		<width>5</width>
		<altitudeMode>relativeToSeaFloor</altitudeMode>
		<color>ff0000ff</color>
		<color>normal</color>
	  </LineStyle>
	 </Style>
	  <name>cell</name>
	  <LookAt>
		<longitude>-75.4005</longitude>
		<latitude>40.853</latitude>
		<tilt>0</tilt>
		<range>6800</range>
		<altitudeMode>relativeToSeaFloor</altitudeMode>
	  </LookAt>
    """
    footer = """
    </Placemark>
</kml>
<!--UNCLASSIFIED-->
    """
    for cell in cell_list:
        cell_kml = """
        <LineString>
	  <styleUrl>#cell</styleUrl>
		<extrude>1</extrude> <!--this is a comment-->
		<coordinates>

        %s

		</coordinates>
	  </LineString>
        """ % cell
        header += cell_kml
    # create recursive function to append node co-ords to kml

if __name__ == "__main__":  # The function calls in this section will be executed when this script is run from the command line

    cell_created = False
    filter_data = False
    cell_cordinates = []
    cell_count = 0
    for input in sys.argv:
        if "-h" == input:
            Helpfunc()
        if "--help" == input:
            Helpfunc(True)
        if "cell" == input and sys.argv.count("cell") == 1:
            find_index = sys.argv.index(input) + 1
            if sys.argv[find_index][-4:] == ".csv":
                print("Generating cell list from file")
                cell_cordinates = Generate_cell_list(sys.argv[find_index])
                with open("analysis_meta.txt","a") as fp:
                    fp.write(cell_cordinates)
            else:
                end_index = find_index + 5
                cell_cordinates = [x for x in sys.argv[find_index:end_index]]
                cell_cordinates = " ".join(cell_cordinates)
                # print(cell_cordinates)
            cell_created = True
        if "cell" == input and sys.argv.count("cell") > 1 and not cell_created:
            cell_count = sys.argv.index(input, cell_count, len(sys.argv))
            # print(cell_count)
            find_index = cell_count + 1
            end_index = find_index + 4
            cell_count = end_index
            cell = [x for x in sys.argv[find_index:end_index]]
            cell = " ".join(cell)
            cell_cordinates.append(cell)
            # print(cell_cordinates)
            # print(len(sys.argv) - cell_count)
            if len(sys.argv) - cell_count < 4:
                cell_created = True
        if "query" == input:
            find_index = sys.argv.index(input) + 1
            end_index = find_index + 5
            extent = [x for x in sys.argv[find_index:end_index]]
            extent = ",".join(extent)
            # print(extent)
            with open("analysis_meta.txt","w+") as fp:
                fp.write(extent)
            PrimaryQ(extent)
        if "filter_version" == input:
            find_index = sys.argv.index(input) + 1
            version = int(sys.argv[find_index])
            # print(version)
            filter_data = True
        if "distance" == input:
            find_index = sys.argv.index(input) + 1
            distance = float(sys.argv[find_index])
            # print(distance)
            filter_data = True

    if filter_data:
        if "distance" not in dir():
            distance = 0
        Filter_csv(version=version, min_distance=distance)

    if cell_created:
        SecondQ(cell_cordinates)

    ##   These are some example program calls that have been configured
    #     overpass_work.py --help                                                  Show the help message
    #     overpass_work.py query 40.0853,-75.4005,40.1186,-75.3549                 Initialize an overpass api query
    #     overpass_work.py filter_version 2 distance .05                           Filter the data from the initial overpass api query and accept a user specified distance
    #     overpass_work.py cell 40.08 -75.4 40.09 -75.38                           Run the refined query and analyze data inside defined cell
    #     overpass_work.py cell 40.08 -75.4 40.09 -75.38 cell 50 -76 51 -76.5      Generate a list of cells to be analyzed\n\n