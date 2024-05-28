# Codes for Odakyu project in terms of POI utilisation and attraction index calculation
#
# Created by Yi on 25 May 2024.
#
from tqdm import tqdm
from pathlib import Path

import pandas as pd
import geopandas as gpd
import numpy as np
import statsmodels.api as sm
import matplotlib.pyplot as plt
import seaborn as sns

from scipy.stats import entropy
from sklearn.preprocessing import minmax_scale
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


def factorise(data: pd.DataFrame, keep_zero: bool = False):
    """Log-transform for variables"""
    # convert variables
    for key in data.columns:
        if key in ['station', 'category']:
            continue

        if keep_zero and not data[data[key] == 0].empty:
            data[key] = np.log(data[key] + 1)
        else:
            data[key] = np.log(data[key])

    return data


def add_measure(full: pd.DataFrame, poi: pd.DataFrame, near: pd.DataFrame, category: str) -> tuple:
    """
    Compute measures (indicators) near a station and add them up in the dataset

    :param full: the full dataframe with all POIs even not near stations
    :param poi: the POIs near a station
    :param near: the dataframe with selected POIs near a station
    :param category: the specific category for computation
    :return: a list of variables
    """
    # compute Y=reviews (i->j, reviews, inflows)
    g_ij = near['rating_votes_count'].dropna().mean()
    # compute k_ij
    k_ij = entropy(near['rating_value'].dropna().values)
    if k_ij == 0:
        k_ij = np.nan
    # compute v_i1
    v_i1 = len(poi)
    # TODO: compute v_i2 when population data is ready
    # compute w_j1
    w_j1 = len(near[near['rating_value'] > 0]) / len(poi)
    # compute w_j2
    selected = full[full['secondary'] == category]
    pi = selected['primary'].unique()[0]
    omega = (len(selected) / len(full[full['primary'] == pi]))
    count = near[['id', 'category']].groupby('category').count().reset_index()
    count = count['id'].values
    p = (count * (count - 1)).sum() / (count * (count.sum() - 1)).sum()
    w_j2 = 1 - omega * p
    # compute d_ij
    d_ij = near['distance'].mean()
    return [g_ij, k_ij, v_i1, w_j1, w_j2, d_ij], ['g', 'k', 'v1', 'w1', 'w2', 'd']


def baseline(d: pd.DataFrame,
             dmap: pd.DataFrame,
             station: pd.DataFrame,
             save: Path = Path('figures'),
             radius: float = 2) -> pd.DataFrame:
    """Add on factors such as accessibility, reviews (place_topics) and rating.
    The data structure should be a bilateral i->j form and k-th , e.g.
    stop_i, category_j, X_i, X_j, d_ij, ...

    :param d: the odakyu dataframe
    :param dmap: distance map for all POIs and stations
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
        for c, g in p.groupby('secondary'):
            row, keys = add_measure(d, p, g, c)
            rows += [[stop, c] + row]

    # create the dataset
    dat = pd.DataFrame(rows, columns=['station', 'category'] + keys)
    dat = factorise(dat)
    dat.replace([np.inf, -np.inf], np.nan, inplace=True)
    # run baseline model for estimating the overall attractiveness
    dat = dat.dropna(how='any')
    model = sm.OLS(dat['g'], dat[keys[1:]])
    results = model.fit(cov_type='HC1')
    print(results.summary())

    # run subsamples for station-specific attractiveness
    att_by_station = []
    for stop, g in tqdm(dat.groupby('station'), desc='By station fitting'):
        m = sm.OLS(g['g'], g[keys[1:]])
        fitted = m.fit(cov_type='HC1')
        att_by_station += [[stop] + fitted.params.loc[['w1', 'w2']].tolist()]

    att_by_station = pd.DataFrame(att_by_station, columns=['id', 'attract1', 'attract2'])
    att_by_station = att_by_station.merge(station[['id', 'name']], on='id', how='left')
    att_by_station = att_by_station.sort_values('attract2', ascending=True)

    # simplified plotting
    fig = plt.figure(figsize=(8, 10))
    plt.plot(att_by_station.att.values, range(len(att_by_station)))
    plt.yticks(range(len(att_by_station)), att_by_station.name.tolist(), rotation=0)
    plt.tight_layout()
    plt.margins(0.01)
    fig.savefig(save / f'attract-by-station-{get_timestamp()}.png', format='png', dpi=150)
    plt.show()
    return dat


def extended(d: pd.DataFrame,
             dmap: pd.DataFrame,
             purpose: pd.DataFrame,
             station: pd.DataFrame,
             save: Path,
             radius: float = 2) -> pd.DataFrame:
    """
    Modified / advanced model where a few changes could be made,
    - distance could be adjusted by price_level
    - opening time / popular times, workdays / weekends
    - accessibility (wheels)

    :param d: the odakyu dataframe
    :param dmap: distance map for all POIs and stations
    :param station: the station info dataframe
    :param save: path for saving the dataframe
    :param radius: a float radius that limits POIs selected
    """
    # family groups
    fgroups = ['aged family', 'single family', 'family with pets', 'nuclear family', 'acessibility family', 'tourist']
    # build the dataset
    rows = []
    d['cid'] = d['cid'].astype(str)
    stops = station['id'].tolist()
    # for each station, we get poi and then extract variables
    for stop in tqdm(stops, desc='Building'):
        p = get_poi_by_station(d, dmap, stop, radius)
        # for a specific category j
        for c, g in p.groupby('secondary'):
            # get Y=reviews (i->j, reviews, inflows)
            gdist = purpose.loc[purpose['secondary'] == c, fgroups].astype(int)
            gdist = gdist.values / gdist.values.sum()
            y = g['rating_votes_count'].dropna().sum()
            if y == np.nan:  # only have unrated POIs
                continue

            y_group = (y * gdist).round(0).tolist()
            # get distances
            di = g['distance'].mean()
            # get X_i using number of POIs around the station or total passengers
            xi = len(g)
            # get ∑X_j*n_jk, k should be extracted from purpose
            # NB. regardless of the n_jk, will obtain a gross-level indicator
            # by extending the columns for 6 groups to xj1 ... xj6, the model can be mapped to different groups
            xj = g['rating_value'].dropna().mean()
            # get alpha_ij
            a = entropy(g['rating_value'].dropna().values)
            if a == 0:
                continue

            rows += [[stop, c, di, a, xi, xj] + y_group[0]]

    ynames = [f'y_{i}' for i in range(len(fgroups))]
    dat = pd.DataFrame(rows, columns=['station', 'category', 'distance', 'alpha', 'xi', 'xj'] + ynames)
    dat = factorise(dat, keep_zero=True)
    # run subsamples for demographic-specific attractiveness
    att_by_demo = []
    for stop, g in tqdm(dat.groupby('station'), desc='By station fitting'):
        for i, f in enumerate(fgroups):
            m = sm.OLS(g[f'y_{i}'], g[['distance', 'alpha', 'xi', 'xj']])
            fitted = m.fit(cov_type='HC1')
            att_by_demo += [
                [stop, f, fitted.params.loc['xj'], fitted.pvalues.loc['xj']] + fitted.conf_int().loc['xj'].to_list()]

    att_by_demo = pd.DataFrame(att_by_demo, columns=['id', 'group', 'attract', 'pvalue', 'lower', 'upper'])
    att_by_demo = att_by_demo.merge(station[['id', 'name']], on='id', how='left')
    att_by_demo = att_by_demo.sort_values('attract', ascending=True)

    # before plotting in the heatmap, minmax it
    att4plot = pd.DataFrame()
    for _, g in att_by_demo.groupby('id'):
        g['norm_group'] = minmax_scale(g['attract'])
        att4plot = pd.concat([att4plot, g], axis=0)

    att4plot['norm_all'] = minmax_scale(att4plot['attract'])
    # use heatmap for attractiveness representation
    grouped = att4plot.pivot(index='id', columns='group', values='attract')
    totaled = att4plot.pivot(index='id', columns='group', values='norm_all')
    att4plot['train'] = att4plot['id'].apply(lambda x: x[:2])

    # fig = plt.figure(figsize=(3, 21), dpi=120)
    fig, axes = plt.subplots(3, 1, sharex=True, figsize=(5, 15))
    for idx, (train, g) in enumerate(att4plot.groupby('train')):
        # make the figure
        g = g.pivot(index='id', columns='group', values='attract')
        im = sns.heatmap(g, cmap="RdYlGn_r", cbar=False, ax=axes[idx], linewidth=1, alpha=0.8)
        # axes[idx].set_yticklabels(labels=g.index, rotation=60, fontsize=14)
        # axes[idx].set_ylabel(ylabel=f'{train}', rotation=90, fontsize=14, labelpad=12)
        # axes[idx].set_xticklabels(labels=fgroups, fontsize=14, rotation=90, horizontalalignment='center')

    mappable = im.get_children()[0]
    cbar = plt.colorbar(mappable, ax=axes, pad=0.1, orientation='vertical')
    cbar.ax.tick_params(rotation=90, labelsize=14)
    # plt.savefig(save / 'heatmap.png', dpi=200, bbox_inches='tight')
    plt.show()

    # im = sns.heatmap(grouped, cmap="RdYlGn_r", cbar=True, linewidth=1, alpha=0.8)
    # plt.yticks(range(len(fgroups)), labels=fgroups, fontsize=14)
    # plt.xticks(range(len(att4plot)), att4plot['id'].tolist(), fontsize=14)
    # cbar = plt.colorbar(im.get_children()[0], pad=0.02, orientation='vertical')
    # cbar.ax.tick_params(rotation=90, labelsize=14)
    # plt.show()
    return


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
    station = pd.read_excel('result/odakyu-stops-final.xlsx')
    stops = station['id'].tolist()
    poi = get_poi_by_station(oda, dmap, stops[0])
    # get purpose
    purpose = pd.read_excel('poi/category-list-purpose-annotated.xlsx')

    # load geo data
    pg = gpd.read_file('data/station-passengers-2021/utf8/S12-22_NumberOfPassengers.shp', encoding='utf8')
