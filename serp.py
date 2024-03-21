# The script for Serp APIs
#
# Created by Yi on 19 March 2024.
#

import json
import time
import requests

from tqdm import tqdm
from urllib.parse import urlparse, parse_qs

from pathlib import Path
from utils import get_config, init_logger, insert, create_engine, get_timestamp

# init a logger
logger = init_logger('serp-api')


def get_params(q,
               location: str,
               apikey: str,
               start: int = 0,
               hl: str = 'ja',
               gl: str = 'jp',
               google_domain: str = 'google.co.jp') -> dict:
    """
    Return a resembled parameter pack for querying from API's endpoint.

    :param q: query string, accept array or single string
    :param location: a unified location, usually specific at prefecture level or nation level
    :param apikey: the api-key from serp api
    :param start: the offset for pagination, default 0
    :param hl: language code, https://serpapi.com/google-languages
    :param gl: nation code
    :param google_domain: google search engine, default google.co.jp for Japan market
    """
    # for each query, its format is "<stop> <type>"
    it = dict(q=q, api_key=apikey, location=location, hl=hl, gl=gl, google_domain=google_domain, start=start)
    return it


def create_request(stops: list,
                   keywords: list,
                   apikey: str):
    """
    Return a generator by creating requests based on stops and keywords

    :param stops: a list of stops
    :param keywords: a list of query keywords, e.g. types of POIs
    """
    for sto in stops:
        station = f'{sto[2]} station'
        loc = sto[-1]  # location, prefecture
        for key in keywords:
            q = f'{key} near {station}'
            it = get_params(q=q, location=loc, apikey=apikey)
            yield it


def parse_request(response: requests.models.Response, engine) -> str:
    """
    Parse content of a response and insert records

    :param response: the response body of requests
    :param engine: a sqlalchemy engine
    """

    assert response.status_code == 200, f'Failed at {response.url} with {response.content}'
    data = json.loads(response.content)
    # make cache of responses
    pages = list(data.get('serpapi_pagination', {}).get('other_pages', {}).values())
    meta = data.get('search_metadata', {})
    para = data.get('search_parameters', {})
    # some pages have nothing returned, and it contains `search_information` metadata
    empty_check = data.get('search_information', {})
    rps_records = dict(url=response.url,
                       start=para.get('start', 0),
                       status=meta.get('status', 'Error'),
                       content=str(response.content),
                       processed_at=meta.get('processed_at', ''),
                       json_endpoint=meta.get('json_endpoint', ''),
                       pagination=','.join(pages),
                       timestamp=get_timestamp())
    if empty_check:
        status = empty_check.get('error', 'Error')
        rps_records['status'] = status
        insert(engine, 'response', **rps_records)
        return ''

    insert(engine, 'response', **rps_records)
    # make cache of results
    records = []
    for d in data['local_results']:
        # process specific attributes
        services = ','.join([k for k, v in d.get('service_options', {}).items() if v == 'true'])
        coords = d.get('gps_coordinates')
        lat, lng = list(coords.values()) if coords else 0, 0
        rec = dict(services=services,
                   title=d.get('title', ''),
                   address=d.get('address', ''),
                   coordinates=f'{lat}+{lng}',
                   search_type=' '.join(para['q'].split(' ')[1:]),
                   return_type=d.get('type', ''),
                   rating=d.get('rating', -1),  # neg values mean missing
                   reviews_original=d.get('reviews_original', ''),
                   reviews=d.get('reviews', 0),
                   price=d.get('price', ''),
                   description=d.get('description', ''),
                   place_id=d.get('place_id', ''),
                   place_id_search=d.get('place_id_search', ''),
                   lsig=d.get('lsig', ''),
                   timestamp=get_timestamp())
        records += [rec]

    # insert in bulk
    insert(engine, 'poi', *records)
    # return the next pagination
    logger.info(f'Fetched {len(data["local_results"])} results with query[{para["q"]}]!')
    return data.get('serpapi_pagination', {}).get('next', '')


def get_request(endpoint: str, engine, param: dict = None) -> str:
    """
    Raise requests through API.

    :param endpoint: API endpoint or the next-page url
    :param engine: a sqlalchemy engine
    :param param: parameters for querying
    """
    r = requests.get(endpoint, params=param)
    return parse_request(r, engine)


def request_by_pages(items, endpoint: str, engine):
    """
    Iterative requests running page by page

    See documentation in get_request().
    """
    for idx, param in enumerate(tqdm(items, desc='Requesting')):
        # NB. items are distinct by query keywords, only when pages={},
        # it switches to the next param and page is a dict of pagination
        # ... first request
        next_url = get_request(endpoint, engine=engine, param=param)
        while next_url:  # not empty
            logger.info(f'NextPageFetch[{idx}] {next_url}!')
            next_param = parse_qs(urlparse(next_url).query)
            next_param['apikey'] = param['api_key']
            next_url = get_request(endpoint, engine=engine, param=next_param)

    return


if __name__ == '__main__':
    # fetch conf params
    path = Path('data')
    conf = get_config(Path('conf-serpapi.json'))

    # database config
    sqlite = f'sqlite:///{conf["sqlite"]}'
    engine = create_engine(sqlite)

    # request test
    stops = conf['stops'][:2]
    types = conf['include-types'][:2]
    items = create_request(stops, types, conf['apikey'])
    request_by_pages(items, endpoint=conf['endpoint'], engine=engine)
