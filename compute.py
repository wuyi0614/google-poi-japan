# Codes for Odakyu project in terms of POI utilisation and attraction index calculation
#
# Created by Yi on 25 May 2024.
#
import matplotlib.pyplot as plt
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


def add_factors(d: pd.DataFrame,
                dmap: pd.DataFrame,
                purpose: pd.DataFrame,
                station: pd.DataFrame,
                save: Path,
                radius: float = 2) -> pd.DataFrame:
    """Add on factors such as accessibility, reviews (place_topics) and rating.
    The data structure should be a bilateral i->j form and k-th , e.g.
    stop_i, category_j, X_i, X_j, d_ij, ...

    :param d: the odakyu dataframe
    :param dmap: distance map for all POIs and stations
    :param purpose: the purpose relationship table between population groups and POIs
    :param station: the station info dataframe
    :param save: path for saving the dataframe
    :param radius: a float radius that limits POIs selected
    """
    rows = []
    d['cid'] = d['cid'].astype(str)
    stops = station['id'].tolist()
    # for each station, we get poi and then extract variables
    for stop in tqdm(stops, desc='Building'):
        p = get_poi_by_station(d, dmap, stop)
        # for a specific category j
        for c, g in p.groupby('secondary'):
            # get Y=reviews (i->j, reviews, inflows)
            y = g['rating_votes_count'].dropna().mean()
            if y == np.nan:  # only have unrated POIs
                continue

            # NB. alternatively, use high-rating users
            # g['rater'] = g['rating_distribution'].dropna().apply(lambda x: sum(list(eval(x).values())[:-2]))
            # y = g['rater'].sum()
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

            rows += [[stop, c, y, di, a, xi, xj]]

    # create the dataset
    dat = pd.DataFrame(rows, columns=['station', 'category', 'y', 'distance', 'alpha', 'xi', 'xj'])
    # convert variables
    dat['y'] = np.log(dat['y'])
    dat['distance'] = np.log(dat['distance'])
    dat['alpha'] = np.log(dat['alpha'])
    dat['xi'] = np.log(dat['xi'])
    dat['xj'] = np.log(dat['xj'])
    # run baseline model for estimating the overall attractiveness
    dat = dat.dropna(how='any')
    model = sm.OLS(dat['y'], dat[['distance', 'alpha', 'xi', 'xj']])
    results = model.fit(cov_type='HC1')
    print(results.summary())

    # run subsamples for station-specific attractiveness
    xjs = []
    for stop, g in tqdm(dat.groupby('station'), desc='Subsample fitting'):
        m = sm.OLS(g['y'], g[['distance', 'alpha', 'xi', 'xj']])
        fitted = m.fit(cov_type='HC1')
        xjs += [[stop, fitted.params.loc['xj']]]

    att = pd.DataFrame(xjs, columns=['id', 'att'])
    att = att.merge(station[['id', 'name']], on='id', how='left')
    att = att.sort_values('att', ascending=True)

    fig = plt.figure(figsize=(8, 10))
    plt.plot(att.att.values, range(len(att)))
    plt.yticks(range(len(att)), att.name.tolist(), rotation=0)
    plt.tight_layout()
    plt.margins(0.01)
    fig.savefig('result/attraction.png', format='png', dpi=100)
    plt.show()
    return dat


def gravity_model(d: pd.DataFrame):
    """
    Modified / advanced model where a few changes could be made,
    - distance could be adjusted by price_level
    - opening time / popular times
    - accessibility (wheels)

    :param d:
    :return:
    """

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
