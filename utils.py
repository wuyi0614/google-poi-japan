# Basic utilities for processing
#
# Created by Yi on 18 March 2024.
#

import json

from pathlib import Path
from datetime import datetime

from sqlalchemy import TEXT, Integer, Float, Column
from sqlalchemy import create_engine
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


# pre-defined table objects
TABLES = {'response': Response, 'poi': POI}
LOGGER = init_logger('database')


def insert(engine, tbl: str, *args, **kwargs):
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
        return

    session.add_all(records)
    session.commit()
    session.close()
    LOGGER.info(f'Insert {len(records)} records into table[{tbl}]!')
    return


if __name__ == '__main__':
    # init the database by mocking it
    sqlite = 'sqlite:///data/japan-poi.db'
    engine = create_engine(sqlite)
    # delete all tables
    Base.metadata.drop_all(engine)
    # rebuild all tables
    Base.metadata.create_all(engine)
    assert (Path('data') / 'japan-poi.db').is_file(), 'Database mocking failed!'
