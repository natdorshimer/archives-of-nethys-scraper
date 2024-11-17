import argparse
import json
import os
from dataclasses import dataclass

import requests

from scrape_aon import get_all_aon_json_data_and_save


@dataclass(frozen=True)
class Args:
    aon_version: str


def parse_args() -> Args:
    parser = argparse.ArgumentParser(description='Scrape images from Archives of Nethys')
    parser.add_argument('--version', type=str, help='Version of Archives of Nethys to scrape from', default='39')
    args = parser.parse_args()
    return Args(args.version)


def list_all_files_in_dir(directory: str) -> list[str]:
    return [os.path.join(directory, file) for file in os.listdir(directory)]


def scrape_all_images(aon_version: str) -> None:
    output_dir = os.path.join('aon-data', aon_version)
    json_files = list_all_json_files(output_dir)

    if len(json_files) == 0:
        print(f'No JSON files found in {output_dir}. Scraping from AON.')
        get_all_aon_json_data_and_save(aon_version, False)
        json_files = list_all_json_files(output_dir)

    for file in json_files:
        with open(file) as f:
            data = json.load(f)
            for item in data:
                get_webp_file_and_save(item, output_dir)


def list_all_json_files(output_dir):
    return [os.path.join(output_dir, file) for file in os.listdir(output_dir) if file.endswith('.json')]


def main():
    args = parse_args()
    aon_version = f'aon{args.aon_version}'
    output_dir = os.path.join('aon-data', aon_version)
    os.makedirs(output_dir, exist_ok=True)

    scrape_all_images(aon_version)


directory_cache = set()


def make_dir_if_not_exists(file_path: str) -> None:
    if file_path not in directory_cache:
        os.makedirs(file_path, exist_ok=True)
        directory_cache.add(file_path)


def get_webp_file_and_save(aon_entity: dict[str, any], output_dir: str) -> None:
    if 'image' not in aon_entity:
        return

    image_paths: list[str] = aon_entity['image']

    for image_path in image_paths:
        if image_path.startswith('/'):
            image_path = image_path[1:]

        file_name = os.path.join(output_dir, image_path)
        file_path_without_file_name = '/'.join(file_name.split('/')[:-1])

        if os.path.exists(file_name):
            print(f'{file_name} already exists')
            return

        make_dir_if_not_exists(file_path_without_file_name)

        creature_name = aon_entity['name']

        url = f'https://2e.aonprd.com/{image_path}'
        response = requests.get(url)
        print(f'Downloaded {creature_name} from {url}')

        if response.status_code == 200:
            with open(file_name, 'wb') as f:
                f.write(response.content)
        elif response.status_code == 404:
            print(f'{image_path} does not exist')
        else:
            print(f'Failed to download {creature_name} with status code {response.status_code}')


if __name__ == '__main__':
    main()
