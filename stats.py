# The basic statistics tools for calculation
#
# Created by Yi on 06 May 2024.
#

import geopandas as gpd

from math import radians, sin, cos, asin, sqrt
from collections import namedtuple

from tqdm import tqdm

from utils import insert, get_timestamp


def quick_measure(c1, c2, unit="km"):
    lon1, lat1 = c1.lng, c1.lat
    lon2, lat2 = c2.lng, c2.lat
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    d_lon = lon2 - lon1
    d_lat = lat2 - lat1
    a = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lon / 2) ** 2
    c = 2 * asin(sqrt(a))
    r = 6371  # the earth's radius, unit: km
    return round(c * r, 3) if unit == "km" else round(c * r * 1000, 1)


def map_on_point(c, coords: list):
    """Map distances between a given coord and a list of coords"""

    def gen(c, coords):
        for each in coords:
            if each:
                yield c, each
            else:
                continue

    def func(pack, unit="km"):
        return quick_measure(*pack, unit=unit)

    out = [func(p) for p in gen(c, coords)]
    return out


# create a Coord namedtuple
Coord = namedtuple('Coord', ['lng', 'lat'])


def neighbour_compute(src: gpd.GeoDataFrame,
                      tar: gpd.GeoDataFrame,
                      to_tbl: str,
                      engine,
                      step: int = 100,
                      buffer: int = 1000,
                      to_poi: str = 'odakyu'):
    """
    Find neighbouring points around target points

    :param src: candidate points
    :param tar: target points
    :param to_tbl: a table name for data saving
    :param engine: a sqlite3 engine
    :param step: batch size for computing, default 100
    :param buffer: buffer size (radius) for geopandas's geometry, default 1000 meters
    :param to_poi: a table name for poi saving in sqlite3
    :return: None
    """
    # to make sure the unit of buffer is meter, use EPSG:3857 as crs
    for i in range(0, len(src), step):
        comm = src.iloc[i: (i + step), :]
        x = tar.buffer(buffer).unary_union

        nearby = comm["geometry"].intersection(x)
        confirmed = comm[~nearby.is_empty]
        if confirmed.empty:
            continue

        confirmed = confirmed.drop(columns='geometry')
        rds = confirmed.to_dict(orient='records')
        # calculate distances between POIs and stations
        coords = [Coord(lng, lat) for lng, lat in zip(tar['lng'], tar['lat'])]
        items = []
        for each in rds:
            c = Coord(each['longitude'], each['latitude'])
            ds = map_on_point(c, coords)  # DO NOT parallel if namedtuple cannot be pickled
            # create an item for the distance table
            item = {i: j for i, j in zip(tar['id'], ds)}
            item['cid'] = each['cid']
            item['timestamp'] = get_timestamp()
            items += [item]

        # insert distance results
        insert(*items, engine=engine, tbl=to_tbl)
        # insert selected pois
        insert(*rds, engine=engine, tbl=to_poi)

    # completed
    return


def match_land_price(src: gpd.GeoDataFrame,
                     tar: gpd.GeoDataFrame,
                     key: str,
                     buffer: int = 2000):
    """
    Search and match nearby POIs using a buffer zone!

    :param src: A geo-dataframe with geometry
    :param tar: B geo-dataframe with geometry
    :param key: the key for additional info
    :param buffer: buffer size (radius)
    """
    src['price'] = 0
    for idx in tqdm(src.index, desc='Nearby Searching'):
        row = src.loc[[idx], :]
        x = row.buffer(buffer).unary_union
        nearby = tar['geometry'].intersection(x)
        confirmed = tar.loc[~nearby.is_empty, :]
        if confirmed.empty:
            print(f'Error at row {idx}, no data was found!')

        src.loc[idx, 'price'] = confirmed[key].mean()

    return src
