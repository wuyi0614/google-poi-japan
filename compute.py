# Computing codes for Odakyu project in terms of POI categorisation and attraction index calculation
#
# Created by Yi on 23 May 2024.
#

import re
import openai
import pandas as pd

from pathlib import Path
from itertools import chain
from collections import Counter
from ast import literal_eval
from random import sample

from utils import get_timestamp, create_engine, openaix


def auto_poi_categorise(client: openai.Client,
                        items: list,
                        categories: list = None,
                        **kwargs) -> list:
    """
    Automatically implement POI categorisation through a GPT model

    :param client: an openai Client object
    :param items: a list of unstructured categories
    :param categories: the categories for automatic summary, default None, which will enforce GPT to run itself
    :param kwargs: params for GPT, incl. prompt, max_tokens, model, etc.
    :return: a list of structured categories
    """
    entities = set(items)
    cate = ','.join(categories)
    model = 'gpt-4o'
    results = []

    while True:
        if len(entities) == 0:
            break  # stop when entities are used up

        ents = sample(entities, 10 if len(entities) > 10 else len(entities))
        entities = entities.difference(ents)  # update by diff from sets
        ents = ','.join(ents)
        # create the prompt
        if categories is None:
            prompt = """Please classify the following map entities into a list of categories and return in the following JSON format: 
                     {{"primary": "category", "secondary": ["entities"]}}, and make sure every entity should be well classified by its semantic name.
                     Here is the list of map entities {} separated by ",".""".format(ents)
        else:
            prompt = """Please classify the following map entities into the list of provided Categories and return in the following JSON format: 
            {{"primary": "Category", "secondary": ["entities"]}}, and make sure every entity should be well classified by its semantic name.
            Here is the list of map entities {} separated by "," and here are the provided Categories: {} separated by "," """.format(
                ents, cate)

        messages = [{"role": "system",
                     "content": "You are professional in semantically annotating map entities and point of interests"},
                    {"role": "user", "content": prompt}]
        try:
            feed = openaix(client, text='', messages=messages, model=model)
            res = [literal_eval(it) for it in re.findall(r'{.*}', feed)]
            results += res
        except Exception as e:
            print(f'Error for {ents} at position: {len(entities)}')
            break

    return results


if __name__ == '__main__':
    import json

    # load poi data
    sqlite = 'sqlite:///data/tokyo-poi.db'
    engine = create_engine(sqlite)
    # retrieve POI table and deduplicate and the correct number of POIs is about 193,728!
    oda = pd.read_sql_table('odakyu', engine)
    oda = oda[~oda[['title', 'description']].duplicated()]
    # retrieve unique POI categories
    cate = list(chain(*oda.loc[~oda['category_ids'].isna(), 'category_ids'].apply(lambda x: eval(x)).values.tolist()))
    uni_cate = Counter(cate)  # a key-value formed counted return
    uni_cate = pd.DataFrame(uni_cate, index=[0]).T.reset_index()
    uni_cate.columns = ['category', 'count']
    uni_cate.to_excel(f'poi/poi-category-count-{get_timestamp()}.xlsx', index=False)

    # load ai config
    conf = json.loads(Path('conf.json').read_text(encoding='utf8'))
    openai_api_key = conf['openai-api-key']
    client = openai.Client(api_key=openai_api_key)
    # test auto poi categorisation
    items = uni_cate['category'].tolist()
    categories = ['Life service', 'Public service', 'Medical service',
                  'Dining', 'Accommodation', 'Workplace', 'Education', 'Transportation',
                  'Finance', 'Recreation', 'Tourist attraction', 'Pet', 'Shopping', 'Others']
