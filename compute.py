# Codes for Odakyu project in terms of POI utilisation and attraction index calculation
#
# Created by Yi on 25 May 2024.
#

import json
import datetime

from tqdm import tqdm
from pathlib import Path

import pandas as pd
import numpy as np
import statsmodels.api as sm

from scipy.stats import entropy
from utils import get_timestamp, create_engine


def get_stats(d: pd.DataFrame):
    """Get stats about count/percent in each categories"""
    c1 = d[['secondary', 'cid']].groupby('secondary').count().reset_index()
    c2 = d[['primary', 'cid']].groupby('primary').count().reset_index()

    c = d[['primary', 'secondary']].drop_duplicates().merge(c1, on='secondary', how='left')
    c = c.merge(c2, on='primary', how='left')
    c = c.sort_values(by=['primary', 'secondary'], ascending=True)
    c.columns = ['primary', 'secondary', 'secondary#', 'primary#']
    c['secondary%'] = c['secondary#'] / c['secondary#'].sum()
    c['primary%'] = c['primary#'] / c['secondary#'].sum()
    return c


def get_poi_by_station(d: pd.DataFrame, dmap: pd.DataFrame, station_id: str, radius: float = 2):
    """
    Return a subset dataframe with selected POIs

    :param d: the POI dataframe
    :param dmap: distance map for all POIs and stations
    :param station_id: a string-like station id, like TO01
    :param radius: a float radius that limits POIs selected
    :return:
    """
    # use station id to extract distance table from database
    assert station_id in dmap.columns, f'Invalid {station_id} not in dmap!'
    r = dmap.loc[dmap[station_id] <= radius, ['cid', station_id]]
    r.columns = ['cid', 'distance']
    o = d[d['cid'].isin(r['cid'].astype(str).tolist())]
    o = o.merge(r, on='cid')
    return o


def factorise(data: pd.DataFrame, keep_zero: bool = False, keep_nan: bool = False):
    """Log-transform for variables"""
    # convert variables
    for key in data.columns:
        if key in ['station', 'category']:
            continue

        if keep_zero and not data[data[key] == 0].empty:
            data[key] = np.log(data[key] + 1)
        else:
            data[key] = np.log(data[key])

    if not keep_nan:
        data.replace([np.inf, -np.inf], np.nan, inplace=True)
        data = data.dropna(how='any')

    print(f'Factorised {len(data)} rows of valid records!')
    return data


def _extended_accessibility(near: pd.DataFrame) -> float:
    """
    The extended version of accessibility taking into account the availability
    of time and facilities.

    :param near: the dataframe with selected POIs near a station
    :return: the value of accessibility
    """

    # process facility
    def _convert_attribute(x):
        if not isinstance(x, str):
            return 0

        attr = json.loads(x).get('available_attributes', [0])
        return 0 if attr is None else len(attr) + 0

    # process opening time
    def _get_time(op: dict = None, cl: dict = None):
        b = datetime.datetime(year=2024, month=1, day=1, second=0)
        if op is None:
            return b

        # if close < open, day + 1
        if int(cl['hour']) <= int(op['hour']):  # 0 am and 0 am!!
            diff = (b + datetime.timedelta(hours=24 + int(cl['hour']), minutes=int(cl['minute']))) \
                   - (b + datetime.timedelta(hours=int(op['hour']), minutes=int(op['minute'])))
        else:
            diff = (b + datetime.timedelta(hours=int(cl['hour']), minutes=int(cl['minute']))) \
                   - (b + datetime.timedelta(hours=int(op['hour']), minutes=int(op['minute'])))
        return diff.total_seconds() / 3600  # return hours!

    def _convert_time(x: str):
        # convert the long string-like item into readable time
        if x == np.nan:
            return 0

        times = json.loads(x)['work_hours']['timetable']
        if times is None:  # for those closed or without opening info
            return 0

        ti = []
        for day, t in times.items():
            if t is None:
                continue

            ops = [_get_time(it['open'], it['close']) for it in t]
            ti += [sum(ops) / 24]

        return (sum(ti) / len(ti)) * (len(ti) / 7) if ti else 0

    def _convert(x: str, a: str):
        return _convert_time(x) * _convert_attribute(a)

    acc = near[['work_time', 'attributes']].apply(lambda x: _convert(x.iloc[0], x.iloc[1]), axis=1)
    return acc.sum() / len(acc)


def add_measure(stop: pd.Series,
                full: pd.DataFrame,
                poi: pd.DataFrame,
                near: pd.DataFrame,
                purpose: pd.DataFrame,
                category: str) -> tuple:
    """
    Compute measures (indicators) near a station and add them up in the dataset

    :param stop: the station series with price info added
    :param full: the full dataframe with all POIs even not near stations
    :param poi: the POIs near a station
    :param near: the dataframe with selected POIs near a station
    :param purpose: the dataframe maps relationship between POI categories and demographics
    :param category: the specific category for computation
    :return: a list of variables
    """
    fgroups = ['aged family', 'single family', 'family with pets', 'nuclear family', 'accessibility family', 'tourist']

    # compute gij=reviews (i->j, reviews, inflows)
    g_ij = near['rating_votes_count'].dropna().sum()

    # compute demographic-targeting Y
    gdist = purpose.loc[purpose['secondary'] == category, fgroups].astype(int)
    gdist = gdist.values / gdist.values.sum()
    g_ijk = (g_ij * gdist).round(0).tolist()[0]

    # compute k_ij
    k_ij = entropy(near['rating_value'].dropna().values)
    if k_ij == 0:
        k_ij = np.nan

    # compute v_i1
    v_i1 = len(poi) / len(full)
    # compute v_i2
    v_i2 = stop['price'].values[0]
    # TODO: compute w_j1, but c_ij(r_ij>0) is insufficient, resulting too huge coef.
    w_j1 = len(near) / len(poi)
    # compute extended-version w_j1
    gdist[gdist > 0] = 1
    w_jk1 = (_extended_accessibility(near) * gdist).tolist()[0]

    # compute w_j2
    selected = full[full['secondary'] == category]
    pi = selected['primary'].unique()[0]
    omega = (len(selected) / len(full[full['primary'] == pi]))
    count = near[['id', 'category']].groupby('category').count().reset_index()
    count = count['id'].values
    if count.sum() <= 1:
        w_j2 = 1
    else:
        p = (count * (count - 1)).sum() / (count * (count.sum() - 1)).sum()
        w_j2 = 1 - omega * p

    # compute d_ij
    d_ij = near['distance'].mean()

    # return values and varnames
    values = [g_ij] + g_ijk + [k_ij, v_i1, v_i2, w_j2, d_ij] + [w_j1] + w_jk1
    keys = ['g'] + [f'g[{k}]' for k in fgroups] + ['k', 'v1', 'v2', 'w2', 'd', 'w1'] + [f'w1[{k}]' for k in fgroups]
    return values, keys


def baseline(d: pd.DataFrame,
             dmap: pd.DataFrame,
             purpose: pd.DataFrame,
             station: pd.DataFrame,
             save: Path = Path('result'),
             radius: float = 2) -> pd.DataFrame:
    """Add on factors such as accessibility, reviews (place_topics) and rating.
    The data structure should be a bilateral i->j form and k-th , e.g.
    stop_i, category_j, X_i, X_j, d_ij, ...

    :param d: the odakyu dataframe
    :param dmap: distance map for all POIs and stations
    :param purpose: the dataframe maps relationship between POI categories and demographics
    :param station: the station info dataframe
    :param save: path for saving the dataframe
    :param radius: a float radius that limits POIs selected
    """
    rows = []
    d['cid'] = d['cid'].astype(str)
    stops = station['id'].tolist()
    # for each station, we get poi and then extract variables
    for stop in tqdm(stops, desc='Building'):
        p = get_poi_by_station(d, dmap, stop, radius)
        # for a specific category j
        s = station.loc[station['id'] == stop]
        for c, g in p.groupby('secondary'):
            row, keys = add_measure(s, d, p, g, purpose, c)
            rows += [[stop, c] + row]

    # create the dataset
    variables = ['k', 'v1', 'v2', 'w1', 'w2', 'd']
    dat = pd.DataFrame(rows, columns=['station', 'category'] + keys)
    dat = factorise(dat, keep_zero=True)
    dat.to_excel(save / f'baseline-index-{get_timestamp()}.xlsx', index=False)
    model = sm.OLS(dat['g'], dat[variables])
    results = model.fit(cov_type='HC1')
    print(results.summary())

    # run subsamples for station-specific attractiveness
    att_by_station = []
    for stop, g in tqdm(dat.groupby('station'), desc='By station fitting'):
        m = sm.OLS(g['g'], g[variables])
        fitted = m.fit(cov_type='HC1')
        att_by_station += [[stop] + fitted.params.loc[['w1', 'w2']].tolist()]

    att_by_station = pd.DataFrame(att_by_station, columns=['id', 'attract1', 'attract2'])
    att_by_station = att_by_station.merge(station[['id', 'name']], on='id', how='left')
    att_by_station['attract'] = att_by_station['attract1'] + att_by_station['attract2']
    att_by_station = att_by_station.sort_values('attract', ascending=True)
    att_by_station.to_excel(save / f'attract-by-station-{get_timestamp()}.xlsx', index=False)
    return dat


def extended(d: pd.DataFrame,
             dmap: pd.DataFrame,
             purpose: pd.DataFrame,
             station: pd.DataFrame,
             save: Path = Path('result'),
             radius: float = 2) -> pd.DataFrame:
    """
    Modified / advanced model where a few changes could be made,
    - distance could be adjusted by price_level
    - opening time / popular times, workdays / weekends
    - accessibility (wheels)

    :param d: the odakyu dataframe
    :param dmap: distance map for all POIs and stations
    :param purpose: the dataframe maps relationship between POI categories and demographics
    :param station: the station info dataframe
    :param save: path for saving the dataframe
    :param radius: a float radius that limits POIs selected
    """
    # family groups
    fgroups = ['aged family', 'single family', 'family with pets', 'nuclear family', 'accessibility family', 'tourist']
    # build the dataset
    rows = []
    d['cid'] = d['cid'].astype(str)
    stops = station['id'].tolist()
    # for each station, we get poi and then extract variables
    for stop in tqdm(stops, desc='Building'):
        p = get_poi_by_station(d, dmap, stop, radius)
        s = station.loc[station['id'] == stop]
        # for a specific category j
        for c, g in p.groupby('secondary'):
            row, keys = add_measure(s, d, p, g, purpose, c)
            rows += [[stop, c] + row]

    dat = pd.DataFrame(rows, columns=['station', 'category'] + keys)
    dat.describe().T.round(3).to_excel(save / f'summary-stats-{get_timestamp()}.xlsx')
    dat = factorise(dat, keep_zero=True, keep_nan=False)
    dat.to_excel(save / f'extended-index-{get_timestamp()}.xlsx', index=False)

    # run subsamples for demographic-specific attractiveness
    att_by_demo, rsquare = [], []
    regs = pd.DataFrame()
    genkeys = ['k', 'v1', 'v2', 'w2', 'd']
    for stop, g in tqdm(dat.groupby('station'), desc='By station fitting'):
        for i, f in enumerate(fgroups):
            m = sm.OLS(g[f'g[{f}]'], g[genkeys + [f'w1[{f}]']])
            fitted = m.fit(cov_type='HC0')
            att_by_demo += [[stop, f] + fitted.params.loc[[f'w1[{f}]', 'w2']].tolist()]
            # collect reg results in SI
            r = pd.DataFrame({'param': fitted.params, 'pvalue': fitted.pvalues, 'ci_lower': fitted.conf_int()[0],
                              'ci_upper': fitted.conf_int()[1]})
            r['name'] = stop
            r['group'] = f
            regs = pd.concat([regs, r], axis=0)
            rsquare += [fitted.rsquared_adj]

    # output regs params
    regs.to_excel(save / f'regs-by-demographic-{get_timestamp()}.xlsx')
    att_by_demo = pd.DataFrame(att_by_demo, columns=['id', 'group', 'attract1', 'attract2'])
    att_by_demo = att_by_demo.merge(station[['id', 'name']], on='id', how='left')
    att_by_demo['attract'] = att_by_demo['attract1'] + att_by_demo['attract2']
    att_by_demo = att_by_demo.sort_values('attract', ascending=True)
    att_by_demo.to_excel(save / f'attract-by-demographic-{get_timestamp()}.xlsx', index=False)
    return dat


if __name__ == '__main__':
    # global conf
    save = Path('result')

    # NB. might use the additional data for calculation of attraction
    oda_file = Path('poi') / 'categories-odakyu-poi-2k-2024-05-25 10-43-38.csv'
    oda = pd.read_csv(oda_file)

    # get statistics
    stat = get_stats(oda)
    stat.to_excel(save / f'stats-categories-{get_timestamp()}.xlsx', index=False)

    # how to utilise the reviews and rating info
    drop_keys = ['feature_id', 'address_info_borough', 'address_info_address',
                 'address_info_zip', 'address_info_country_code', 'place_id', 'phone',
                 'domain', 'main_image', 'snippet', 'is_claimed', 'additional_categories',
                 'time_update', 'check_url']
    oda = oda.drop(columns=drop_keys)
    head = oda.head(100)

    # processing attribute for accessibility + reservation/book/menu as convenience using
    # `local_business_links` column + `url` + `contacts`
    sqlite = 'sqlite:///data/tokyo-poi.db'
    engine = create_engine(sqlite)
    dmap = pd.read_sql_table('odakyu2k', engine)  # you DO NOT have to use odakyu1k because it's a subset of odakyu2k

    # get stations
    station = pd.read_excel('result/odakyu-stops-with-price.xlsx')

    # test for poi and station
    stops = station['id'].tolist()
    poi = get_poi_by_station(oda, dmap, stops[0])

    # get purpose
    purpose = pd.read_excel('poi/category-list-purpose-annotated.xlsx')

    # run models
    dbase = baseline(oda, dmap, purpose, station)
    dext = extended(oda, dmap, purpose, station)
