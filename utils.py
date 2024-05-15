# Basic utilities for processing
#
# Created by Yi on 18 March 2024.
#

import json
import pandas as pd

from pathlib import Path
from datetime import datetime

from sqlalchemy import TEXT, Integer, Float, Column
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import declarative_base, sessionmaker

from loguru import logger

# mock the default database
Base = declarative_base()

# create logging path
DEFAULT_LOG_DIR = Path('logs')
DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)


def init_logger(name, out_dir=None, level='INFO'):
    logger.remove()  # remove the initial handler

    if out_dir is None:
        out_dir = DEFAULT_LOG_DIR

    out_name = out_dir / name
    logger.add(out_name.with_suffix(".log"), format="{time} {level} {message}", level=level)
    return logger


def get_timestamp(fmt: str = '%Y-%m-%d %H:%M:%S'):
    return datetime.now().strftime(fmt)


def get_config(path: Path):
    """Get configuration from a local conf file"""
    f = Path(path)
    return json.loads(f.read_text(encoding='utf8'))


# create the database table
class Response(Base):
    __tablename__ = 'response'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='incremental ids for records')

    # query-related info
    url = Column(TEXT, comment='url for query with params')
    start = Column(Integer, comment='pagination start point')

    # response-related info
    status = Column(TEXT, comment='status code in return')
    content = Column(TEXT, comment='response body')
    processed_at = Column(TEXT, comment='scraping time from API')
    json_endpoint = Column(TEXT, comment='json cache from API')
    pagination = Column(TEXT, comment='pagination separated by commas')

    # logging
    timestamp = Column(TEXT, comment='timestamp for each record')


class POI(Base):
    __tablename__ = 'poi'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='incremental ids for records')

    # columns from Google local research
    services = Column(TEXT, comment='service options separated by commas')
    coordinates = Column(TEXT, comment='gps coords in format of lat+lng')
    title = Column(TEXT, comment='full name of POI')
    address = Column(TEXT, comment='full address of POI')
    search_type = Column(TEXT, comment='searched type from Google Search Types')
    return_type = Column(TEXT, comment='returned type from Google search results, e.g. 居酒屋')
    rating = Column(Float, comment='user rating')
    reviews_original = Column(TEXT, comment='displayed reviews')
    reviews = Column(Integer, comment='user reviews')
    price = Column(TEXT, comment='price level/range')
    description = Column(TEXT, comment='description from scraping')
    place_id = Column(TEXT, comment='place id from SerpApi for re-doing')
    place_id_search = Column(TEXT, comment='search url for the specific place id')
    lsig = Column(TEXT, comment='uuid')

    # logging
    timestamp = Column(TEXT, comment='timestamp for each record')


class Odakyu(Base):
    __tablename__ = 'odakyu'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='incremental ids for records')
    # columns for Google Business Listing data
    title = Column(TEXT)
    description = Column(TEXT)
    category = Column(TEXT)
    category_ids = Column(TEXT)
    additional_categories = Column(TEXT)
    cid = Column(TEXT)
    feature_id = Column(TEXT)
    address = Column(TEXT)
    address_info_borough = Column(TEXT)
    address_info_address = Column(TEXT)
    address_info_city = Column(TEXT)
    address_info_zip = Column(TEXT)
    address_info_region = Column(TEXT)
    address_info_country_code = Column(TEXT)
    place_id = Column(TEXT)
    phone = Column(TEXT)
    url = Column(TEXT)
    domain = Column(TEXT)
    logo = Column(TEXT)
    main_image = Column(TEXT)
    total_photos = Column(Integer)
    snippet = Column(TEXT)
    latitude = Column(Float)
    longitude = Column(Float)
    is_claimed = Column(TEXT)
    attributes = Column(TEXT)
    place_topics = Column(TEXT)
    rating_rating_type = Column(TEXT)
    rating_value = Column(Float)
    rating_votes_count = Column(Float)
    rating_rating_max = Column(TEXT)
    rating_distribution = Column(TEXT)
    people_also_search = Column(TEXT)
    work_time = Column(TEXT)
    popular_times = Column(TEXT)
    local_business_links = Column(TEXT)
    contacts = Column(TEXT)
    time_update = Column(TEXT)
    check_url = Column(TEXT)
    price_level = Column(TEXT)
    hotel_rating = Column(TEXT)
    # logging
    timestamp = Column(TEXT, comment='timestamp for each record')


class Odakyu1k(Base):
    __tablename__ = 'odakyu1k'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='incremental ids for records')
    cid = Column(TEXT)
    OH01 = Column(Float)
    OH02 = Column(Float)
    OH03 = Column(Float)
    OH04 = Column(Float)
    OH05 = Column(Float)
    OH06 = Column(Float)
    OH07 = Column(Float)
    OH08 = Column(Float)
    OH09 = Column(Float)
    OH10 = Column(Float)
    OH11 = Column(Float)
    OH12 = Column(Float)
    OH13 = Column(Float)
    OH14 = Column(Float)
    OH15 = Column(Float)
    OH16 = Column(Float)
    OH17 = Column(Float)
    OH18 = Column(Float)
    OH19 = Column(Float)
    OH20 = Column(Float)
    OH21 = Column(Float)
    OH22 = Column(Float)
    OH23 = Column(Float)
    OH24 = Column(Float)
    OH25 = Column(Float)
    OH26 = Column(Float)
    OH27 = Column(Float)
    OH28 = Column(Float)
    OH29 = Column(Float)
    OH30 = Column(Float)
    OH31 = Column(Float)
    OH32 = Column(Float)
    OH33 = Column(Float)
    OH34 = Column(Float)
    OH35 = Column(Float)
    OH36 = Column(Float)
    OH37 = Column(Float)
    OH38 = Column(Float)
    OH39 = Column(Float)
    OH40 = Column(Float)
    OH41 = Column(Float)
    OH42 = Column(Float)
    OH43 = Column(Float)
    OH44 = Column(Float)
    OH45 = Column(Float)
    OH46 = Column(Float)
    OH47 = Column(Float)
    OH48 = Column(Float)
    OH49 = Column(Float)
    OH50 = Column(Float)
    OH51 = Column(Float)
    OE01 = Column(Float)
    OE02 = Column(Float)
    OE03 = Column(Float)
    OE04 = Column(Float)
    OE05 = Column(Float)
    OE06 = Column(Float)
    OE07 = Column(Float)
    OE08 = Column(Float)
    OE09 = Column(Float)
    OE10 = Column(Float)
    OE11 = Column(Float)
    OE12 = Column(Float)
    OE13 = Column(Float)
    OE14 = Column(Float)
    OE15 = Column(Float)
    OE16 = Column(Float)
    OT01 = Column(Float)
    OT02 = Column(Float)
    OT03 = Column(Float)
    OT04 = Column(Float)
    OT05 = Column(Float)
    OT06 = Column(Float)
    OT07 = Column(Float)
    timestamp = Column(TEXT, comment='timestamp for each record')


class Odakyu2k(Base):
    __tablename__ = 'odakyu2k'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='incremental ids for records')
    cid = Column(TEXT)
    OH01 = Column(Float)
    OH02 = Column(Float)
    OH03 = Column(Float)
    OH04 = Column(Float)
    OH05 = Column(Float)
    OH06 = Column(Float)
    OH07 = Column(Float)
    OH08 = Column(Float)
    OH09 = Column(Float)
    OH10 = Column(Float)
    OH11 = Column(Float)
    OH12 = Column(Float)
    OH13 = Column(Float)
    OH14 = Column(Float)
    OH15 = Column(Float)
    OH16 = Column(Float)
    OH17 = Column(Float)
    OH18 = Column(Float)
    OH19 = Column(Float)
    OH20 = Column(Float)
    OH21 = Column(Float)
    OH22 = Column(Float)
    OH23 = Column(Float)
    OH24 = Column(Float)
    OH25 = Column(Float)
    OH26 = Column(Float)
    OH27 = Column(Float)
    OH28 = Column(Float)
    OH29 = Column(Float)
    OH30 = Column(Float)
    OH31 = Column(Float)
    OH32 = Column(Float)
    OH33 = Column(Float)
    OH34 = Column(Float)
    OH35 = Column(Float)
    OH36 = Column(Float)
    OH37 = Column(Float)
    OH38 = Column(Float)
    OH39 = Column(Float)
    OH40 = Column(Float)
    OH41 = Column(Float)
    OH42 = Column(Float)
    OH43 = Column(Float)
    OH44 = Column(Float)
    OH45 = Column(Float)
    OH46 = Column(Float)
    OH47 = Column(Float)
    OH48 = Column(Float)
    OH49 = Column(Float)
    OH50 = Column(Float)
    OH51 = Column(Float)
    OE01 = Column(Float)
    OE02 = Column(Float)
    OE03 = Column(Float)
    OE04 = Column(Float)
    OE05 = Column(Float)
    OE06 = Column(Float)
    OE07 = Column(Float)
    OE08 = Column(Float)
    OE09 = Column(Float)
    OE10 = Column(Float)
    OE11 = Column(Float)
    OE12 = Column(Float)
    OE13 = Column(Float)
    OE14 = Column(Float)
    OE15 = Column(Float)
    OE16 = Column(Float)
    OT01 = Column(Float)
    OT02 = Column(Float)
    OT03 = Column(Float)
    OT04 = Column(Float)
    OT05 = Column(Float)
    OT06 = Column(Float)
    OT07 = Column(Float)
    timestamp = Column(TEXT, comment='timestamp for each record')


# pre-defined table objects
# TABLES = {'response': Response, 'poi': POI}
TABLES = {'odakyu': Odakyu, 'odakyu1k': Odakyu1k, 'odakyu2k': Odakyu2k}
LOGGER = init_logger('database')


def insert(*args, engine, tbl: str, **kwargs):
    """Append records into the database

    :param engine: a sqlalchemy engine
    :param tbl: the table name in the database
    :param args: a list of records
    :param kwargs: a record split by kwargs
    """
    session = sessionmaker(engine)()
    table = TABLES[tbl]
    if args:  # single insert
        records = [table(**item) for item in args]

    elif kwargs:  # bulk insert
        records = [table(**kwargs)]

    else:
        LOGGER.info(f'Insert 0 records into table[{tbl}]!')
        session.close()
        return

    session.add_all(records)
    session.commit()
    session.close()
    LOGGER.info(f'Insert {len(records)} records into table[{tbl}]!')
    return


def read(engine, tbl: str):
    """Read a table from sqlite3 database"""
    d = pd.read_sql_table(tbl, engine)
    return d


if __name__ == '__main__':
    # init the database by mocking it
    sqlite = 'sqlite:///data/tokyo-poi.db'
    engine = create_engine(sqlite)
    # delete all tables
    Base.metadata.drop_all(engine)
    # rebuild all tables
    Base.metadata.create_all(engine)
    assert (Path('data') / 'tokyo-poi.db').is_file(), 'Database mocking failed!'
