# The main parsers for Google's business listing data
#
# Created by Yi on 05 May 2024.
#

import re
import csv
import json

from collections import defaultdict
from typing import Union

import pandas as pd
import geopandas as gpd
import numpy as np

from tqdm import tqdm
from pathlib import Path

from utils import get_timestamp, insert, create_engine
from stats import neighbour_compute


def checking(chunk: pd.DataFrame, cnt: dict = None):
    """
    A quick checker for a summary of key params, including
        - rating.value
        - rating.votes_count
        - rating_distribution
        - price_level
        - category_ids
        - attributes
        - place_topics, basically review keywords

    :param chunk: a chunk of CSV
    :param cnt: an iterable dictionary
    :return: a dict
    """

    # how many ratings
    keys = ['rating.value', 'rating.votes_count', 'rating_distribution',
            'price_level', 'category_ids', 'attributes', 'place_topics']
    cnt = defaultdict(int) if cnt is None else cnt
    for k in keys:
        mask = chunk[k].isna()
        cnt[k] += len(chunk[~mask])

    return cnt


def get_category(chunk: pd.DataFrame, cnt: dict = None):
    """
    Summarise different categories using a mapping between cids and category_ids

    :param chunk: a chunk of CSV
    :param cnt: an iterable dictionary with keys=categories
    :return: a dict
    """
    if cnt is None:
        cnt = defaultdict(list)

    # process category first
    for c, sub in chunk[['category_ids', 'cid']].groupby('category_ids'):
        if c == np.nan:
            continue

        cc = re.findall(r'"([\w]+)"', c)
        for foo in cc:
            cnt[foo] += sub['cid'].to_list()

    return cnt


def get_city(chunk: pd.DataFrame, level: str = 'region', cnt: dict = None):
    """
    Summarise city-specific POI distribution

    :param chunk: a chunk of CSV
    :param level: city, zip or region (country but not necessary)
    :param cnt: an iterable dictionary with keys=cities
    :return: a dict
    """
    if cnt is None:
        cnt = defaultdict(list)

    for c, sub in chunk[[f'address_info.{level}', 'cid']].groupby(f'address_info.{level}'):
        if c == np.nan:
            continue

        cnt[c] += sub['cid'].to_list()

    return cnt


def retrieve_by_region(fname: Path,
                       size: int,
                       region: Union[str, list],
                       save: Path,
                       to_tbl: str,
                       engine=None):
    """
    Iteratively retrieve data by specific region or regions

    :param fname: a filepath for datafile
    :param size: chunksize for CSV loading
    :param region: a specific region name or a list of regions for matching
    :param save: a filepath for saving with filename
    :param to_tbl: a table name for data saving
    :param engine: optional, if save ends with '.db', engine must be specified
    :return: a dataframe
    """
    count = 0
    re_region = '|'.join(region)
    for i, chunk in enumerate(tqdm(pd.read_csv(fname, chunksize=size), desc='Load chunks')):
        columns = [i.replace('.', '_') for i in chunk.columns.values.tolist()]
        chunk.columns = columns
        mask = chunk['address_info_region'].str.match(f'{re_region}').fillna(False)
        out = chunk[mask] if region else chunk
        # counting records
        count += len(out)
        # different I/O options
        if save.suffix == '.csv':
            with open(str(save), 'w', encoding='utf8') as csf:
                # write into csv file by rows
                writer = csv.writer(csf)
                if i == 0:
                    writer.writerow(out.columns.to_list())

                writer.writerows(out.values.tolist())

        elif save.suffix == '.db' and engine is not None:
            out['cid'] = out['cid'].astype(str)
            rds = out.to_dict(orient='records')
            # NB. tablename is fixed as listing!
            insert(*rds, engine=engine, tbl=to_tbl)

    print(f'Found {count} rows in {re_region}!')
    return out


def retrieve_by_neighbours(fname: Path,
                           neighbours: gpd.GeoDataFrame,
                           buffer: int,
                           to_tbl: str,
                           size: int = 10000,
                           step: int = 1000):
    """
    :param fname: a filepath for datafile
    :param neighbours: a dataframe of neighbour points, e.g. stations
    :param buffer: a radius that finds POIs within the circle, or a list of buffers
    :param to_tbl: a table name for data saving
    :param size: chunksize for CSV loading
    :param step: how big a chunck for geometry matching
    :return: a dataframe
    """
    # convert df.poi into gpd.poi, and Google's default crs=4326
    for chunk in tqdm(pd.read_csv(fname, chunksize=size), desc='Load chunks'):
        columns = [i.replace('.', '_') for i in chunk.columns.values.tolist()]
        chunk.columns = columns
        g = gpd.GeoDataFrame(chunk, geometry=gpd.points_from_xy(chunk.longitude, chunk.latitude), crs='EPSG:4326')
        g = g.to_crs('EPSG:3857')
        # find intersection between the chunk and neighbours and dump into sqlite3 db
        g['cid'] = g['cid'].astype(str)
        neighbour_compute(g, neighbours, to_tbl, engine, step=step, buffer=buffer)

    return


def retrieve_by_cid(engine, from_tbl: str, cid: list, save: Path, fname: str, crs: str='EPSG:4326'):
    """
    Retrieve and dump data by a list of cids

    :param engine: a sqlite3 engine for loading
    :param from_tbl: a table name for data loading
    :param cid: a list of cid (google ids)
    :param save: a filepath for saving with filename
    :param fname: a string-like filename
    :param crs: crs schema, default for 3857
    :return: a dataframe
    """
    chunk = pd.read_sql_table(from_tbl, engine)
    chunk = chunk.drop(columns='id')
    out = chunk[chunk['cid'].isin(cid)].drop_duplicates()
    # NB. to_file does not work with M2 chips
    # out = gpd.GeoDataFrame(out, geometry=gpd.points_from_xy(out.longitude, out.latitude), crs=crs)
    # out.to_file(str(save / f'{fname}-{get_timestamp()}.shp'), encoding='utf8')
    # instead, use csv but convert longitude and latitude into 3857 schema
    out.to_csv(str(save / f'{fname}-{get_timestamp()}.csv'), index=False, encoding='utf8')
    return out


if __name__ == '__main__':
    # facts: 1) 8,649,685 POIs in total, 2) 4,173 POI types
    size = 10000
    fname = Path('data') / 'japan-listing.csv'
    count_check, count_category = None, None
    count_city = None
    for chunk in tqdm(pd.read_csv(fname, chunksize=size), desc='Load chunks'):
        # count_check = checking(chunk, count_check)
        count_category = get_category(chunk, count_category)
        count_city = get_city(chunk, 'region', count_city)

    # cache category mapping and checking statistics
    save = Path('result')
    # pd.DataFrame(count_check, index=[0]).to_excel(save / f'checking-{get_timestamp()}.xlsx', index=False)
    (save / f'category-mapping-{get_timestamp()}.json').write_text(json.dumps(count_category))
    (save / f'city-mapping-{get_timestamp()}.json').write_text(json.dumps(count_city))

    # retrieve Tokyo data
    sqlite = 'sqlite:///data/tokyo-poi.db'
    engine = create_engine(sqlite)
    odakyu_regions = ['Tokyo', '東京都', 'tokyo', 'Kanagawa', 'kanagawa', '神奈川縣', '神奈川']
    retrieve_by_region(fname, size, region=odakyu_regions,
                       save=Path(sqlite), to_tbl='odakyu', engine=engine)

    # retrieve station-nearby POIs
    file = Path('result') / 'odakyu-stops-final-2024-05-06.xlsx'
    neighbours = pd.read_excel(file)
    # see how buffer and crs works:
    # https://stackoverflow.com/questions/74333139/how-to-make-a-buffer-have-specific-latitude-and-longitude-coordinates-in-geopand
    neighbours = gpd.GeoDataFrame(neighbours, geometry=gpd.points_from_xy(neighbours.lng, neighbours.lat),
                                  crs='EPSG:4326').to_crs('EPSG:3857')
    # retrieve both 1/2k buffered POIs
    # NB. produce duplicates if the two lines are separately executed!!!
    retrieve_by_neighbours(fname, neighbours, buffer=1000, to_tbl='odakyu1k', size=10000)
    retrieve_by_neighbours(fname, neighbours, buffer=2000, to_tbl='odakyu2k', size=10000)

    # retrieve cids
    cids_1k = pd.read_sql_table('odakyu1k', engine)['cid'].tolist()
    cids_2k = pd.read_sql_table('odakyu2k', engine)['cid'].tolist()
    k1 = retrieve_by_cid(engine, 'odakyu', cids_1k, save, 'odakyu-listing1k')
    k2 = retrieve_by_cid(engine, 'odakyu', cids_2k, save, 'odakyu-listing2k')
