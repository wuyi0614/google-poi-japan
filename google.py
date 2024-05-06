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

ENDPOINT_NEARBY = 'https://places.googleapis.com/v1/places:searchNearby'
ENDPOINT_TEXT = 'https://places.googleapis.com/v1/places:searchText'


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


def google_nearby_search(apikey: str):
    """Depreciated function since its pagination is not desirable!!!"""
    client = googlemaps.Client(key=apikey)
    params = dict(
        location=[35.5271464711313, 139.43821501651442],  # lat lon of The White House
        radius=100,  # radius in meters
        page_token=None,  # page token for going to next page of search
        language='en')
    # or use way # method 2
    place_type = ''
    page1 = client.places_nearby(type=place_type, **params)
    # token for searching next page; to be used in a loop

    params['page_token'] = page1['next_page_token']
    page2 = client.places_nearby(type=place_type, **params)

    rs = []
    for p in [page1, page2]:
        rs += [r['name'] for r in p['results']]


def google_place_search(apikey, q: str, fields: list = None):
    """Search places with texts"""
    if fields is None:
        fields = ['formatted_address', 'name', 'geometry', 'place_id', 'types']

    client = googlemaps.Client(key=apikey)
    page = client.find_place(input=q, input_type='textquery', fields=fields, language='en')
    points = page['candidates']

    assert len(points) > 0, f'Found nothing on {q}'
    return points


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
    response = requests.post(ENDPOINT_NEARBY,
                             json=item.dict(),
                             headers=headers)
    save = Path('data')
    places = get_places(response, save)

    # test google place search
    stops = conf['stops']
    stations = []
    for i, stop in enumerate(stops[42:]):
        stations += google_place_search(apikey, q=f'{stop[2]} Station')

    # convert results into a dataframe
    out = pd.DataFrame(stations)
    out['lat'] = out['geometry'].apply(lambda x: x['location']['lat'])
    out['lng'] = out['geometry'].apply(lambda x: x['location']['lng'])
    # merge searched stops with stop info
    sto = pd.DataFrame(stops, columns=['id', 'title', 'name', 'region'])
    sto['name'] = sto['name'].apply(lambda x: f"{x} Station")
    sto.to_excel(save / f'odakyu-stops-{get_timestamp()}.xlsx', index=False)
    out = out.merge(sto, on='name', how='left')
    out.to_excel(save / f'odakyu-stops-updated-{get_timestamp()}.xlsx', index=False)
    # the final version: odakyu-stops-final-2024-05-06.xlsx
