# The script for Google Map Services APIs
#
# Created by Yi on 18 March 2024.
#

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import googlemaps
from pydantic import BaseModel

from utils import get_config

ENDPOINT = 'https://places.googleapis.com/v1/places:searchNearby'


class BasicRequest(BaseModel):
    """The basic request body with general params"""
    includedTypes: list = []
    maxResultCount: int = 20
    rankPreference: str = 'DISTANCE'
    locationRestriction: dict = {}
    # see https://www.unicode.org/cldr/charts/latest/supplemental/territory_language_information.html


def get_timestamp():
    """Return a string-like timestamp: mmddHHMMSS"""
    return datetime.now().strftime('%m%d%H%M%S')


def get_request(loc: list,
                radius: float,
                include_types: list = [],
                include_primary_types: list = [],
                max_results: int = 20,
                rank: str = 'DISTANCE'):
    """
    Create a request body given the above params.
    See include_types at: https://developers.google.com/maps/documentation/places/web-service/place-types?hl=zh-cn
    """
    loc = {
        'circle': {
            'center': {
                'latitude': loc[0],
                'longitude': loc[1]
            },
            'radius': radius
        }}
    # NB. if includeTypes is '', it returns everything
    it = BasicRequest(includedTypes=include_types,
                      maxResultCount=max_results,
                      locationRestriction=loc,
                      rankPreference=rank)
    return it


def get_headers(api_key: str, fields: list, **params):
    """
    The basic headers for a basic request.
    See all fields at https://developers.google.com/maps/documentation/places/web-service/nearby-search?hl=zh-cn.
    """
    it = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': api_key,
        'X-Goog-FieldMask': ','.join(fields)  # use , to separate fields
    }
    it.update(**params)
    return it


def get_places(r: requests.models.Response,
               save: Path = None) -> pd.DataFrame:
    """Parse the response and return a friendly dictionary"""
    assert r.status_code == 200, f'Failed: {r.content}'
    d = json.loads(r.content)['places']
    li = []
    for it in d:
        it['types'] = ','.join(it["types"])
        it['location'] = list(it['location'].values())
        it['displayName'] = it['displayName']['text']
        li += [it]

    if save:
        pd.DataFrame(li).to_csv(save / f'query-{get_timestamp()}.csv', index=False)

    return pd.DataFrame(li)


def google_search(apikey: str):
    client = googlemaps.Client(key=apikey)
    params = dict(
        location=[35.5271464711313, 139.43821501651442], # lat lon of The White House
        radius=100,  # radius in meters
        page_token=None,  # page token for going to next page of search
        language='en')
    # or use way # method 2
    place_type = ''
    page1 = client.places_nearby(type=place_type, **params)
    # token for searching next page; to be used in a loop

    params['page_token'] = page1['next_page_token']
    page2 = client.places_nearby(type=place_type, **params)

    params['page_token'] = page2['next_page_token']
    page3 = client.places_nearby(type=place_type, **params)

    rs = []
    for p in [page1]:
        rs += [r['name'] for r in p['results']]


def run():
    pass


if __name__ == '__main__':
    # a generalised test
    # specify the local conf file
    conf_path = Path('conf.json')
    conf = get_config(conf_path)
    # specify params
    # fields = conf['x-fields']['basic'] + conf['x-fields']['basic']
    fields = ["places.displayName",
              "places.location",
              "places.types",
              "places.priceLevel",
              "places.rating",
              "places.userRatingCount"]
    apikey = conf['api-key']

    headers = get_headers(apikey, fields)
    # 相模原站 - [35.515252302635176, 139.42266412504938]
    # 相武台前 - [35.49960504276268, 139.41149755708128]
    item = get_request(loc=[35.49960504276268, 139.41149755708128],
                       radius=80,
                       max_results=20,
                       include_types=[])
    response = requests.post(ENDPOINT,
                             json=item.dict(),
                             headers=headers)
    save = Path('data')
    places = get_places(response, save)
