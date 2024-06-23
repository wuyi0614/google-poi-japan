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
from sklearn.preprocessing import MinMaxScaler
from utils import get_timestamp, create_engine


def get_stats(d: pd.DataFrame):
    """Get stats about count/percent in each categories"""
    c1 = d[['secondary', 'cid']].groupby('secondary').count().reset_index()
    c2 = d[['primary', 'cid']].groupby('primary').count().reset_index()

    c = c1.merge(d[['primary', 'secondary']].drop_duplicates(), on='secondary', how='left')
    c = c.merge(c2, on='primary', how='left')
    c = c.sort_values(by=['primary', 'secondary'], ascending=True)
    c.columns = ['secondary', 'secondary#', 'primary', 'primary#']
    c['secondary%'] = c['secondary#'] / c['secondary#'].sum()
    c['primary%'] = c['primary#'] / c['secondary#'].sum()
    return c


def get_supplement_stats(d: pd.DataFrame):
    rows = []
    for c, g in tqdm(d.groupby('secondary'), desc='Statistics'):
        row = {'Primary Category': g['primary'].unique()[0],
               'Secondary Category': c,
               'No. of Tertiary Categories': g['category'].unique().size,
               'Proportion of Secondary Category': str(len(g)) + ' ({:.1%})'.format(len(g) / len(d))}
        rows += [row]

    out = pd.DataFrame(rows)
    out.sort_values(by=['Primary Category', 'Secondary Category'], ascending=True, inplace=True)
    return out


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
                groups: list,
                clevel: str,
                category: str) -> tuple:
    """
    Compute measures (indicators) near a station and add them up in the dataset

    :param stop: the station series with price info added
    :param full: the full dataframe with all POIs even not near stations
    :param poi: the POIs near a station
    :param near: the dataframe with selected POIs near a station
    :param purpose: the dataframe maps relationship between POI categories and demographics
    :param groups: the list for demographics groups
    :param clevel: the category level, primary, secondary, category
    :param category: the specific category for computation
    :return: a list of variables
    """
    # compute gij=reviews (i->j, reviews, inflows)
    g_ij = near['rating_votes_count'].dropna().sum()
    # compute gij_robust=reviews (over 4-stars)
    g_ij_robust = sum(
        near['rating_distribution'].apply(lambda x: sum(list(eval(x).values())[3:]) if isinstance(x, str) else 0))

    # compute demographic-targeting Y
    gdist = purpose.loc[purpose[clevel] == category, groups].astype(float)
    gdist = gdist.values / gdist.values.sum() if gdist.values.sum() > 0 else np.zeros(len(groups))
    g_ijk = (g_ij * gdist).round(0).flatten().tolist()
    g_ijk_robust = (g_ij_robust * gdist).round(0).flatten().tolist()

    # compute k_ij
    # k_ij = entropy(near['rating_value'].dropna().values)
    k_ij = near['rating_value'].mean()  # Good! average rating as a control variable

    # compute v_i1, being independent of `near` or `category`
    # v_i1 = len(poi) / len(full)
    # v_i1 = entropy(poi['rating_votes_count'].dropna().values)  # Good! use entropy for poi/near
    v_i1 = entropy(poi[['id', 'secondary']].groupby('secondary').count().values.flatten())

    # compute v_i2
    v_i2 = stop['price'].values[0]

    # 1. npj method: sum(delta_j * O_j) / sum(O_j), delta is a threshold function (0/1 within the distance)
    # 2. Hansen(1959) and Levinson and King (2020), f(C_ij) = 1/(1+(C_ij / median(C_ij))
    w_j1 = len(near) / len(full[full[clevel] == category])

    # compute extended-version w_j1
    w_jk1 = (_extended_accessibility(near) * gdist).flatten().tolist()

    # Res Policy - https://www.sciencedirect.com/science/article/pii/S0048733318300702?via%3Dihub#sec0030
    count = near[['id', 'category']].groupby('category').count().reset_index()
    count = count['id'].values
    n = count.sum()  # n --> N for total number of POIs
    if count.sum() <= 1:
        w_j2 = 0
    else:
        # 1. Gini-Simpson index
        # p = ((count * (count - 1)) / (n * (n - 1))).sum()
        # w_j2 = 1 - p  # higher intensity, lower prob of being balanced
        # 2. a new diversity with consideration for low counts!
        #    refer to: https://iopscience.iop.org/article/10.1088/1478-3975/ac264e#pbac264es3
        power = (n - count.size * count) / n  # (N - mn_i) / N
        w_j2 = (1 - 1 / count.size) * sum([(count[i] / n) * np.exp(power[i]) for i in range(count.size)])

    # compute d_ij
    d_ij = near['distance'].mean()

    # return values and varnames
    values = [g_ij, g_ij_robust] + g_ijk + g_ijk_robust + [k_ij, v_i1, v_i2, w_j2, d_ij] + [w_j1] + w_jk1
    keys = (['g', 'gr'] + [f'g[{k}]' for k in groups] + [f'gr[{k}]' for k in groups] +
            ['k', 'v1', 'v2', 'w2', 'd', 'w1'] + [f'w1[{k}]' for k in groups])
    return values, keys


def panelise(d: pd.DataFrame,
             dmap: pd.DataFrame,
             purpose: pd.DataFrame,
             station: pd.DataFrame,
             groups: list,
             clevel: str = 'secondary',
             save: Path = Path('result'),
             radius: float = 1) -> pd.DataFrame:
    """
    Panelise the final dataset for regressions.
    The data structure should be a bilateral i->j form and k-th , e.g.
    stop_i, category_j, X_i, X_j, d_ij, ...

    :param d: the odakyu dataframe
    :param dmap: distance map for all POIs and stations
    :param purpose: the dataframe maps relationship between POI categories and demographics
    :param station: the station info dataframe
    :param groups: the list for demographics groups
    :param clevel: the category level, primary, secondary, category
    :param save: path for saving the dataframe
    :param radius: a float radius that limits POIs selected
    """
    rows = []
    d['cid'] = d['cid'].astype(str)
    stops = station['id'].tolist()
    # for each station, we get poi and then extract variables
    for stop in tqdm(stops, desc='Panelising data'):
        p = get_poi_by_station(d, dmap, stop, radius)
        # for a specific category j
        s = station.loc[station['id'] == stop]
        for c, g in p.groupby(clevel):
            row, keys = add_measure(s, d, p, g, purpose, groups, clevel, c)
            rows += [[stop, c] + row]

    # create the dataset
    dat = pd.DataFrame(rows, columns=['station', 'category'] + keys)
    dat.describe().T.round(3).to_excel(save / f'summary-stats-{get_timestamp()}.xlsx')
    dat = factorise(dat, keep_zero=True)
    # output the dataset
    f = save / f'panel-{get_timestamp()}.xlsx'
    dat.to_excel(f, index=False)
    print(f'Saved file at {str(f)}')
    return dat


def baseline(pnl: pd.DataFrame, save: Path = Path('result')) -> pd.DataFrame:
    """Add on factors such as accessibility, reviews (place_topics) and rating.

    :param pnl: the panel data for regressions
    :param save: path for saving the dataframe
    """
    variables = ['k', 'v1', 'v2', 'w1', 'w2', 'd']

    model = sm.OLS(pnl['g'], pnl[variables])
    results = model.fit(cov_type='HC0')
    print(results.summary())

    # run subsamples for station-specific attractiveness
    att_by_station = []
    robust = []
    for stop, g in tqdm(pnl.groupby('station'), desc='By station fitting'):
        m = sm.OLS(g['g'], g[variables])
        fitted = m.fit(cov_type='HC0')
        att_by_station += [[stop] + fitted.params.loc[['w1', 'w2']].tolist()]
        # for robustness check
        m = sm.OLS(g['gr'], g[variables])
        fitted = m.fit(cov_type='HC0')
        robust += [[stop] + fitted.params.loc[['w1', 'w2']].tolist()]

    # output results
    att_by_station = pd.DataFrame(att_by_station, columns=['id', 'attract1', 'attract2'])
    att_by_station = att_by_station.merge(station[['id', 'name']], on='id', how='left')
    att_by_station['attract'] = att_by_station['attract1'] + att_by_station['attract2']
    att_by_station = att_by_station.sort_values('attract', ascending=True)
    att_by_station.to_excel(save / f'attract-by-station-{get_timestamp()}.xlsx', index=False)
    # output robust results
    robust = pd.DataFrame(robust, columns=['id', 'attract1', 'attract2'])
    robust = robust.merge(station[['id', 'name']], on='id', how='left')
    robust['attract'] = robust['attract1'] + robust['attract2']
    robust = robust.sort_values('attract', ascending=True)
    robust.to_excel(save / f'robust-by-station-{get_timestamp()}.xlsx', index=False)
    # output robust results
    return att_by_station


def extended(pnl: pd.DataFrame, save: Path = Path('result')) -> pd.DataFrame:
    """
    Modified / advanced model where a few changes could be made,
    - distance could be adjusted by price_level
    - opening time / popular times, workdays / weekends
    - accessibility (wheels)

    :param pnl: the panel data for regressions
    :param save: path for saving the dataframe
    """
    # run subsamples for demographic-specific attractiveness
    att_by_demo, rsquare = [], []
    robust = []
    regs = pd.DataFrame()
    genkeys = ['k', 'v1', 'v2', 'w2', 'd']
    for stop, g in tqdm(pnl.groupby('station'), desc='By demographic fitting'):
        for i, f in enumerate(groups):
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
            # for robustness check
            m = sm.OLS(g[f'gr[{f}]'], g[genkeys + [f'w1[{f}]']])
            fitted = m.fit(cov_type='HC0')
            robust += [[stop, f] + fitted.params.loc[[f'w1[{f}]', 'w2']].tolist()]

    # output regs params
    regs.to_excel(save / f'regs-by-demographic-{get_timestamp()}.xlsx')
    # output for regression results
    att_by_demo = pd.DataFrame(att_by_demo, columns=['id', 'group', 'attract1', 'attract2'])
    att_by_demo = att_by_demo.merge(station[['id', 'name']], on='id', how='left')
    att_by_demo['attract'] = att_by_demo['attract1'] + att_by_demo['attract2']
    att_by_demo = att_by_demo.sort_values('attract', ascending=True)
    att_by_demo.to_excel(save / f'attract-by-demographic-{get_timestamp()}.xlsx', index=False)
    # output for robust results
    robust = pd.DataFrame(robust, columns=['id', 'group', 'attract1', 'attract2'])
    robust = robust.merge(station[['id', 'name']], on='id', how='left')
    robust['attract'] = robust['attract1'] + robust['attract2']
    robust = robust.sort_values('attract', ascending=True)
    robust.to_excel(save / f'robust-by-demographic-{get_timestamp()}.xlsx', index=False)
    return att_by_demo


if __name__ == '__main__':
    # global conf
    save = Path('result')

    # NB. might use the additional data for calculation of attraction
    oda_file = Path('poi') / 'categories-odakyu-poi-2k-2024-06-22 20-30-49.csv'
    oda = pd.read_csv(oda_file)

    # get statistics
    stat = get_stats(oda)
    stat.to_excel(save / f'stats-categories-{get_timestamp()}.xlsx', index=False)

    # get supplementary statistics
    stat = get_supplement_stats(oda)
    stat.to_excel(save / f'stats-categories-supplement-{get_timestamp()}.xlsx', index=False)

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
    dmap = pd.read_sql_table('odakyu1k', engine)  # use odakyu1k only

    # get stations
    station = pd.read_excel('result/odakyu-stops-with-price.xlsx')

    # test for poi and station
    stops = station['id'].tolist()
    poi = get_poi_by_station(oda, dmap, stops[0])

    # get purpose
    purpose = pd.read_excel('poi/poi-category-purpose-trajectory.xlsx', header=[1])
    purpose.columns = ['primary', 'secondary'] + [f'f{i}' for i in np.arange(10, 70, 10)] + \
                      [f'n{i}' for i in np.arange(10, 70, 10)] + [f'w{i}' for i in np.arange(10, 70, 10)]

    # recalibrate min-max results, NOTE that the following calibrations are all abandoned
    # 1. normalise within a group
    mm = MinMaxScaler()
    for i in np.arange(10, 70, 10):
        purpose[f'w{i}'] = mm.fit_transform(purpose[[f'n{i}']]).flatten()
    # 2. normalise within a category
    w = []
    for i, row in purpose[[f'f{i}' for i in np.arange(10, 70, 10)]].iterrows():
        row = row.values.reshape(len(row), 1)
        w += [mm.fit_transform(row).flatten().tolist()]
    purpose[[f'w{i}' for i in np.arange(10, 70, 10)]] = w
    # 2.5 normalise by total visitors
    fgroups = [f'f{i}' for i in np.arange(10, 70, 10)]
    purpose[[f'w{i}' for i in np.arange(10, 70, 10)]] = purpose[fgroups].values / purpose[fgroups].sum().sum()
    # 3. average by groups
    for i in np.arange(10, 70, 10):
        purpose[f'w{i}'] = mm.fit_transform(purpose[[f'f{i}']] / purpose[f'f{i}'].sum()).flatten()
        # purpose[f'w{i}'] = purpose[f'f{i}'] / purpose[f'f{i}'].sum()

    # run models
    groups = [f'w{i}' for i in np.arange(10, 70, 10)]  # use the original weighted mappings
    dat = panelise(oda, dmap, purpose, station, clevel='secondary', groups=groups, radius=1)
    # dat = pd.read_excel('result/panel-2024-06-23 17-20-35.xlsx')
    rbase = baseline(dat)
    rext = extended(dat)
