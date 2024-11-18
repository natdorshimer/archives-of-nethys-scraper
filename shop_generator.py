import argparse
import math
from dataclasses import dataclass
from enum import Enum

import pandas as pd

from aon_util import AonItemJson
from search_request import TraitRequest, RarityRequest, EquipmentSearchRequest, LevelRequest, \
    ItemWithRunesSearchRequest, get_random_items_by_request


class ShopType(Enum):
    POTION = 'potion'
    ARTIFACT = 'artifact'
    POISON = 'poison'
    WEAPON = 'weapon'
    ARMOR = 'armor'
    ANY = 'any'

    def has_items_with_runes(self) -> bool:
        return self == ShopType.WEAPON or self == ShopType.ARMOR


@dataclass(frozen=True)
class ShopRequest:
    shop_type: ShopType
    level: int
    rarity_request: RarityRequest
    decay: float = 0.5


traits_by_shop_type: dict[ShopType, TraitRequest] = {
    ShopType.POTION: TraitRequest(required_traits=['Potion', 'Consumable']),
    ShopType.ARTIFACT: TraitRequest(required_traits=['Magical'], exclude_traits=['Consumable', 'Tattoo']),
    ShopType.POISON: TraitRequest(required_traits=['Poison', 'Consumable']),
    ShopType.WEAPON: TraitRequest(categories=['weapon']),
    ShopType.ANY: TraitRequest(categories=['equipment', 'weapon'])
}


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


def generate_shop(shop_request: ShopRequest) -> str:
    items = get_random_items_by_request(generate_shop_by_type(shop_request))

    fields = ['name', 'rarity', 'level', 'source', 'price_raw', 'url']
    return to_table_str(items, fields)


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


def generate_shop_by_type(shop_request: ShopRequest) -> EquipmentSearchRequest | ItemWithRunesSearchRequest:
    if shop_request.shop_type.has_items_with_runes():
        return generate_item_with_runes_search_request(shop_request)

    return EquipmentSearchRequest(
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


def generate_item_with_runes_search_request(shop_request: ShopRequest) -> ItemWithRunesSearchRequest:
    return ItemWithRunesSearchRequest(
        level_request=LevelRequest(
            weights=generate_shop_item_weights(shop_request.level, decay=shop_request.decay)
        ),
        weapons=10 if shop_request.shop_type == ShopType.WEAPON else 0,
        armor=10 if shop_request.shop_type == ShopType.ARMOR else 0
    )


def main():
    shop_request = parse_args()
    print(generate_shop(shop_request))


def to_table_str(items: list[AonItemJson], keys: list[str]) -> str:
    data = [{key: getattr(item, key, "") for key in keys} for item in items]
    df = pd.DataFrame(data, columns=keys)
    return df.to_string(index=False)


if __name__ == '__main__':
    main()
