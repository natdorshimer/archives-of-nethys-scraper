from collections import defaultdict
from dataclasses import dataclass

import json
import os
import requests
import argparse


def main() -> None:
    args = parse_args()
    get_all_aon_json_data_and_save(args.aon_version, args.retrieve_all_revisions)


@dataclass
class Args:
    aon_version: str
    retrieve_all_revisions: bool


def parse_args() -> Args:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--version',
        help='Version of Archives of Nethys to scrape data from',
        default='39'
    )

    parser.add_argument(
        '--retrieve-all-revisions',
        action='store_true',
        help='Do not overwrite data if a newer revision is available',
        default=False
    )

    args = parser.parse_args()
    retrieve_all_revisions: bool = args.retrieve_all_revisions
    return Args(args.version, retrieve_all_revisions)


def get_all_aon_json_data_by_category_overwrite_old_revisions(version: str) -> dict[str, list[dict[str, any]]]:
    item_by_category_and_name: defaultdict[str, dict[str, dict[str, any]]] = defaultdict(dict)

    for index in get_aon_pf2e_indices(version):
        data = get_aon_json_data(index)
        for item in data:
            category = item['category']
            name = item['name']

            item_by_name = item_by_category_and_name.setdefault(category, {})

            if name not in item_by_name:
                item_by_name[name] = item

            release_date = item['release_date']
            existing_release_date = item_by_name[name]['release_date']
            if release_date > existing_release_date:
                item_by_name[name] = item

    item_by_category: dict[str, list[dict[str, any]]] = {}
    for category, items in item_by_category_and_name.items():
        item_by_category[category] = list(items.values())

    return item_by_category


def get_all_aon_json_data_by_category_no_overwriting(version: str) -> dict[str, list[dict[str, any]]]:
    item_by_category: defaultdict[str, list[dict[str, any]]] = defaultdict(list)

    for index in get_aon_pf2e_indices(version):
        data = get_aon_json_data(index)
        for item in data:
            category = item['category']
            item_by_category[category].append(item)

    return item_by_category


def get_all_aon_json_data_by_category(version: str, retrieve_all_revisions: bool) -> dict[str, list[dict[str, any]]]:
    if retrieve_all_revisions:
        return get_all_aon_json_data_by_category_no_overwriting(version)
    else:
        return get_all_aon_json_data_by_category_overwrite_old_revisions(version)


def get_all_aon_json_data_and_save(version: str, retrieve_all_revisions: bool) -> None:
    version = f'aon{version}'
    output_dir = os.path.join('aon-data', version)

    remove_files(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    item_by_category: dict[str, list[dict[str, any]]] = get_all_aon_json_data_by_category(version,
                                                                                          retrieve_all_revisions)

    for category, items in item_by_category.items():
        with open(f"{output_dir}/{category}.json", 'w') as f:
            json.dump(items, f, indent=2)


def get_json(url: str) -> any:
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"Failed to retrieve data from {url}. Response status: {response.status_code}")
    return response.json()


def get_aon_pf2e_indices(version: str) -> dict[str, list[str]]:
    index_url = f"https://elasticsearch.aonprd.com/json-data/{version}-index.json"
    return get_json(index_url)


def get_aon_json_data(index_id: str) -> list[dict[str, any]]:
    try:
        print(f"Retrieving data from {index_id}")
        url = f"https://elasticsearch.aonprd.com/json-data/{index_id}.json"
        return get_json(url)
    except Exception as e:
        print(e)
        return []


def remove_files(output_dir: str) -> None:
    if os.path.exists(output_dir):
        for file in os.listdir(output_dir):
            os.remove(os.path.join(output_dir, file)) if file.endswith('.json') else None


if __name__ == "__main__":
    main()
