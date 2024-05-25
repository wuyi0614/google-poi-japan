# Computing codes for Odakyu project in terms of POI categorisation and attraction index calculation
#
# Created by Yi on 23 May 2024.
#

import re
import openai
import pandas as pd

from tqdm import tqdm
from pathlib import Path
from collections import Counter
from ast import literal_eval

from utils import get_timestamp, create_engine, openaix


def auto_poi_categorise(client: openai.Client,
                        items: list,
                        categories: dict = None,
                        save: Path = Path('poi'),
                        **kwargs) -> pd.DataFrame:
    """
    Automatically implement POI categorisation through a GPT model

    :param client: an openai Client object
    :param items: a list of unstructured categories
    :param categories: the categories for automatic summary, default None, which will enforce GPT to run itself
    :param save: path for saving the file, default `poi/`
    :param kwargs: params for GPT, incl. prompt, max_tokens, model, etc.
    :return: a list of structured categories
    """
    model = 'gpt-4o'
    results = []

    for i, ent in enumerate(tqdm(items, desc='GPT Translating')):
        # create the prompt
        if categories is None:
            prompt = """Please classify the following map entities into a list of categories and return in the following JSON format: 
                     {{"primary": "category", "secondary": ["entities"]}}, and make sure every entity should be well classified by its semantic name.
                     Here is the list of map entities {} separated by ",".""".format(ent)
        else:
            prompt = f"""Please learn the semantic mappings in the provided JSON data and the categories: {json.dumps(categories, ensure_ascii=False)}.
                Classify the provided word into a specific Category as well as a Subcategory. If the word doesn't fit any category, label it as 'Other'. 
                Return the result in the following JSON format, excluding empty categories: 
                {{ "Category": {{"Subcategory": ["word"]}} }}. Make sure to exclude any categories or subcategories that are empty.
                Here is the word: "{ent}" and here are the categories: """

        messages = [{"role": "system",
                     "content": "You are professional in semantically annotating map entities and point of interests"},
                    {"role": "user", "content": prompt}]
        try:
            feed = openaix(client, text='', messages=messages, model=model)
            res = [literal_eval(it) for it in re.findall(r'{[\w\W]+}', feed)]
            results += res
        except Exception as e:
            print(f'Error {e} at position: {i}')
            break

    out = []
    for i, r in enumerate(results):
        if 'Category' in r.keys():
            r = r['Category']

        p = list(r.keys())[0]
        if isinstance(r[p], list):
            s = p
            t = r[p][0]
        else:
            s = list(r[p].keys())[0]
            t = r[p][s][0]

        out += [[p, s, t]]

    out = pd.DataFrame(out, columns=['primary', 'secondary', 'tertiary'])
    out = out.drop_duplicates()
    out.to_excel(save / f'auto-poi-categorised-{get_timestamp()}.xlsx', index=False)
    return out


def get_category_list(file: Path, mode: str = 'empty'):
    """Return a dict of categories incl. primary and secondary categories"""
    poi = pd.read_excel(file)
    poi = poi[['primary', 'secondary', 'tertiary']].drop_duplicates()
    poi = poi[~poi['secondary'].isna()]

    cate = {}
    top = poi.sort_values(['primary'])
    for _, row in top.iterrows():
        row = row.to_dict()
        p, s, t = row['primary'], row['secondary'], row['tertiary']
        if p in cate:  # primary tier
            if s in cate[p]:
                if mode == 'empty':
                    continue
                elif mode == 'all':
                    cate[p][s] += [row['tertiary']]
                else:  # mode='single'
                    continue
            else:
                if mode == 'empty':
                    cate[p] = {s: []}
                else:  # mode='single'
                    cate[p][s] = [row['tertiary']]
        else:
            cate[p] = {s: []}
            if mode == 'empty':
                continue
            elif mode == 'all':
                cate[p][s] += [row['tertiary']]
            else:  # mode='single'
                cate[p][s] = [row['tertiary']]

    return cate


if __name__ == '__main__':
    import json

    # general config
    save = Path('poi')

    # load poi data
    sqlite = 'sqlite:///data/tokyo-poi.db'
    engine = create_engine(sqlite)
    # retrieve POI table and deduplicate and the correct number of POIs is about 193,728!
    oda = pd.read_sql_table('odakyu', engine)
    oda = oda.drop(columns='timestamp')  # entirely empty
    oda = oda[~oda[['title', 'description']].duplicated()]
    # retrieve unique POI categories
    cate = oda.loc[~oda['category'].isna(), 'category'].values.tolist()
    uni_cate = Counter(cate)  # a key-value formed counted return
    uni_cate = pd.DataFrame(uni_cate, index=[0]).T.reset_index()
    uni_cate.columns = ['category', 'count']
    uni_cate.to_excel(f'poi/poi-category-count-{get_timestamp()}.xlsx', index=False)

    # load ai config
    conf = json.loads(Path('conf.json').read_text(encoding='utf8'))
    openai_api_key = conf['openai-api-key']
    client = openai.Client(api_key=openai_api_key)

    opt_poi_file = Path('poi') / 'optimal-poi-categorised.xlsx'
    poi = pd.read_excel(opt_poi_file)
    ratio = poi.loc[poi['count'] < 10, 'count'].sum() / poi['count'].sum()
    print(f'Use <10 as threshold, {round(ratio, 3)*100}% of entries have been deleted')
    poi = poi[poi['count'] >= 10]  # remove those with less than 10 POIs

    mask = poi[['primary', 'secondary']].duplicated()
    top = poi.loc[~mask, ['primary', 'secondary']]
    top.sort_values('primary').to_excel(Path('poi') / 'category-list.xlsx', index=False)

    # test auto-labelling with GPT
    categories = get_category_list(opt_poi_file, mode='empty')
    ents = poi.tertiary.tolist()
    results = auto_poi_categorise(client, ents[:1], categories)

    # use oda to find all annotated POIs
    poi.columns = ['category', 'primary', 'secondary', 'count']
    print(f'Unique three-tiered POIs categories have: {len(poi)} entries!')
    selected = oda[oda['category'].isin(poi['category'].tolist())]
    selected = selected.merge(poi[['category', 'primary', 'secondary']], on='category', how='left')
    selected.to_csv(save / f'categories-odakyu-poi-2k-{get_timestamp()}.csv', index=False)
    categories = get_category_list(opt_poi_file, mode='all')
    (save / f'categories-all-{get_timestamp()}.json').write_text(json.dumps(categories))
