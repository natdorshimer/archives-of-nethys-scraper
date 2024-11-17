import argparse
import json
import math
import pandas as pd
import random

from collections import defaultdict
from dacite import from_dict
from dataclasses import dataclass, field
from enum import Enum

sources = [
    "Treasure Vault",
    "GM Core",
    "Player Core",
    "Monster Core",
    "Secrets of Magic",
    "Rage of Elements",
    "Guns & Gears",
    "Gods & Magic",
    "Book of the Dead"
]


@dataclass(frozen=True)
class LevelRequest:
    weights: dict[int, float] = field(default_factory=dict)


@dataclass(frozen=True)
class TraitRequest:
    required_traits: list[str] = field(default_factory=list)
    exclude_traits: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=lambda: ['equipment'])


@dataclass(frozen=True)
class RarityRequest:
    common_number: int
    uncommon_number: int
    rare_number: int
    unique_number: int


@dataclass(frozen=True)
class SearchRequest:
    rarity_request: RarityRequest
    traits: TraitRequest
    level_request: LevelRequest

class ShopType(Enum):
    POTION = 'potion'
    ARTIFACT = 'artifact'
    POISON = 'poison'
    WEAPON = 'weapon'
    ANY = 'any'

traits_by_shop_type: dict[ShopType, TraitRequest] = {
    ShopType.POTION: TraitRequest(required_traits=['Potion', 'Consumable']),
    ShopType.ARTIFACT: TraitRequest(required_traits=['Magical'], exclude_traits=['Consumable', 'Tattoo']),
    ShopType.POISON: TraitRequest(required_traits=['Poison', 'Consumable']),
    ShopType.WEAPON: TraitRequest(categories=['weapon']),
    ShopType.ANY: TraitRequest(categories=['equipment', 'weapon'])
}



@dataclass(frozen=True)
class ShopRequest:
    shop_type: ShopType
    level: int
    rarity_request: RarityRequest
    decay: float = 0.5

@dataclass
class AonItemJson:
    name: str
    rarity: str
    level: int
    url: str
    category: str
    price_raw: str = ''
    source: list[str] = field(default_factory=list)
    trait: list[str] = field(default_factory=list)

def load_equipment_by_category(category: str) -> list[AonItemJson]:
    with open(f'aon-data/aon39/{category}.json') as f:
        equipment = json.load(f)
        return [from_dict(AonItemJson, item) for item in equipment]

def load_equipment(categories: list[str]) -> list[AonItemJson]:
    items = []
    for category in categories:
        items.extend(load_equipment_by_category(category))
    return items


def any_from_list_is_in_list(list1: list[str], list2: list[str]) -> bool:
    return any(item in list1 for item in list2)


def get_random_items(search_request: SearchRequest) -> list[AonItemJson]:
    equipment = load_equipment(search_request.traits.categories)
    items = [item for item in equipment if any_from_list_is_in_list(item.source, sources)]
    items = [item for item in items if
             len(search_request.traits.required_traits) == 0 or any_from_list_is_in_list(
                 item.trait, search_request.traits.required_traits)]
    items = [item for item in items if not any_from_list_is_in_list(item.trait, search_request.traits.exclude_traits)]

    for item in items:
        item.url = f"https://2e.aonprd.com{item.url}"

    return choose_items_by_level_and_rarity(items, search_request)


def choose_items_by_level_and_rarity(items: list[AonItemJson], search_request: SearchRequest) -> list[AonItemJson]:
    items_by_rarity_by_level: dict[str, dict[int, list[AonItemJson]]] = defaultdict(lambda: defaultdict(list))

    for item in items:
        level = item.level
        rarity = item.rarity
        items_by_level = items_by_rarity_by_level[rarity]
        items_by_level[level].append(item)

    final_items = []

    def get_random_item(rarity: str) -> AonItemJson:
        items_by_level = items_by_rarity_by_level[rarity]

        level_to_weight = search_request.level_request.weights.copy()
        for weight in search_request.level_request.weights:
            if weight not in items_by_level:
                level_to_weight.pop(weight)

        if len(level_to_weight) == 0:
            return []

        levels_to_choose = list(level_to_weight.keys())
        weights = list(level_to_weight.values())
        level = random.choices(levels_to_choose, weights=weights)[0]
        return random.choice(items_by_level[level])

    def get_random_items(rarity: str, number: int) -> list[AonItemJson]:
        return [get_random_item(rarity) for _ in range(number)]

    final_items.extend(get_random_items('common', search_request.rarity_request.common_number))
    final_items.extend(get_random_items('uncommon', search_request.rarity_request.uncommon_number))
    final_items.extend(get_random_items('rare', search_request.rarity_request.rare_number))
    final_items.extend(get_random_items('unique', search_request.rarity_request.unique_number))

    return final_items

def to_table_str(items: list[AonItemJson], keys: list[str]) -> str:
    data = [{key: getattr(item, key, "") for key in keys} for item in items]
    df = pd.DataFrame(data, columns=keys)
    return df.to_string(index=False)


def parse_args() -> ShopRequest:
    parser = argparse.ArgumentParser(description='Scrape images from Archives of Nethys')
    parser.add_argument(
        '--type',
        type=str,
        help='Shop type',
        default=ShopType.POTION.value,
        choices=[shop_type.value for shop_type in ShopType],
    )

    parser.add_argument('--level', type=int, help='Shop level', default=3)
    parser.add_argument('--common', type=int, help='Number of common items', default=5)
    parser.add_argument('--uncommon', type=int, help='Number of uncommon items', default=3)
    parser.add_argument('--rare', type=int, help='Number of rare items', default=1)
    parser.add_argument('--unique', type=int, help='Number of unique items', default=0)
    parser.add_argument('--decay', type=float, help='Decay for item level', default=0.5)

    args = parser.parse_args()

    return ShopRequest(
        shop_type=ShopType(args.type),
        level=args.level,
        rarity_request=RarityRequest(
            common_number=args.common,
            uncommon_number=args.uncommon,
            rare_number=args.rare,
            unique_number=args.unique
        )
    )


def main():
    shop_request = parse_args()
    print(generate_shop(shop_request))


def generate_shop_item_weights(shop_level, max_level=30, decay=0.5) -> dict[int, float]:
    weights = {}

    for level in range(max_level + 1):
        if level <= shop_level:
            weights[level] = math.exp((-1) * decay * (shop_level - level))
        elif level == shop_level + 1:
            weights[level] = 0.2
        elif level == shop_level + 2:
            weights[level] = 0.05

    return weights


def generate_shop_by_type(shop_request: ShopRequest) -> SearchRequest:
    return SearchRequest(
        traits=traits_by_shop_type[shop_request.shop_type],
        level_request=LevelRequest(
            weights=generate_shop_item_weights(shop_request.level, decay=shop_request.decay)
        ),
        rarity_request=RarityRequest(
            common_number=shop_request.rarity_request.common_number,
            uncommon_number=shop_request.rarity_request.uncommon_number,
            rare_number=shop_request.rarity_request.rare_number,
            unique_number=shop_request.rarity_request.unique_number
        )
    )


def generate_shop(shop_request: ShopRequest) -> str:
    items = get_random_items(generate_shop_by_type(shop_request))

    fields = ['name', 'rarity', 'level', 'source', 'price_raw', 'url']
    return to_table_str(items, fields)

if __name__ == '__main__':
    main()
