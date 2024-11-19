import argparse
import math
from dataclasses import dataclass
from enum import Enum

import pandas as pd

from aon_item_loader import AonItemJson, LocalFileAonItemLoader
from search_service import TraitRequest, RarityRequest, EquipmentSearchRequest, LevelRequest, \
    ItemWithRunesSearchRequest, SearchService, GeneralSearchRequest


def main():
    shop_request = parse_args()
    sources = [
        "Treasure Vault",
        "GM Core",
        "Player Core",
        "Monster Core",
        "Secrets of Magic",
        "Rage of Elements",
        "Guns & Gears",
        "Gods & Magic",
        "Book of the Dead",
        "Grand Bazaar"
    ]

    search_service = SearchService(LocalFileAonItemLoader(), sources)
    search_request = create_search_request(shop_request)
    items = search_service.get_random_items_by_request(search_request)
    print(_display_as_table_str(items))


class ShopType(Enum):
    POTION = 'potion'
    ARTIFACT = 'artifact'
    POISON = 'poison'
    WEAPON = 'weapon'
    ARMOR = 'armor'
    ANY = 'any'
    BLACKSMITH = 'blacksmith'
    BLACKSMITH_MAGIC = 'blacksmith-magic'

    def has_items_with_runes(self) -> bool:
        return self == ShopType.WEAPON or self == ShopType.ARMOR


@dataclass
class EquipmentShopInfo:
    traits_by_shop_type: TraitRequest


@dataclass
class ItemWithRunesShopInfo:
    weapon_to_armor_proportion: float = 0.5


@dataclass(frozen=True)
class Shop:
    equipment_shop_info: EquipmentShopInfo | None = None
    item_with_runes_shop_info: ItemWithRunesShopInfo | None = None

    def has_items_with_runes(self) -> bool:
        return self.item_with_runes_shop_info is not None

    def has_equipment(self) -> bool:
        return self.equipment_shop_info is not None


shop_by_shop_type = {
    ShopType.POTION: Shop(
        equipment_shop_info=EquipmentShopInfo(
            traits_by_shop_type=TraitRequest(required_traits=['Potion', 'Consumable'])
        )
    ),
    ShopType.ARTIFACT: Shop(
        equipment_shop_info=EquipmentShopInfo(
            traits_by_shop_type=TraitRequest(required_traits=['Magical'], exclude_traits=['Consumable', 'Tattoo'])
        )
    ),
    ShopType.POISON: Shop(
        equipment_shop_info=EquipmentShopInfo(
            traits_by_shop_type=TraitRequest(required_traits=['Poison', 'Consumable'])
        )
    ),
    ShopType.WEAPON: Shop(
        item_with_runes_shop_info=ItemWithRunesShopInfo(weapon_to_armor_proportion=1.0)
    ),
    ShopType.ARMOR: Shop(
        item_with_runes_shop_info=ItemWithRunesShopInfo(weapon_to_armor_proportion=0)
    ),
    ShopType.ANY: Shop(
        equipment_shop_info=EquipmentShopInfo(
            traits_by_shop_type=TraitRequest(categories=['equipment', 'weapon', 'armor'])
        ),
        item_with_runes_shop_info=ItemWithRunesShopInfo()
    ),
    ShopType.BLACKSMITH: Shop(
        equipment_shop_info=EquipmentShopInfo(
            traits_by_shop_type=TraitRequest(categories=['weapon', 'armor'])
        )
    ),
    ShopType.BLACKSMITH_MAGIC: Shop(
        item_with_runes_shop_info=ItemWithRunesShopInfo(
            weapon_to_armor_proportion=0.5
        )
    )
}


@dataclass(frozen=True)
class ShopRequest:
    shop_type: ShopType
    level: int
    rarity_request: RarityRequest
    number: int
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
    parser.add_argument('--number', type=int, help='Number of items for weapons and armor', default=10)
    args = parser.parse_args()

    return ShopRequest(
        shop_type=ShopType(args.type),
        level=args.level,
        number=args.number,
        rarity_request=RarityRequest(
            common_number=args.common,
            uncommon_number=args.uncommon,
            rare_number=args.rare,
            unique_number=args.unique
        ),
        decay=args.decay
    )


def create_search_request(shop_request: ShopRequest) -> GeneralSearchRequest:
    shop: Shop = shop_by_shop_type[shop_request.shop_type]

    weights = _generate_shop_item_weights(shop_request.level, decay=shop_request.decay)

    equipment_search_request = None
    if shop.has_equipment():
        equipment_search_request = EquipmentSearchRequest(
            traits=shop.equipment_shop_info.traits_by_shop_type,
            level_request=LevelRequest(weights),
            rarity_request=shop_request.rarity_request
        )

    item_with_runes_search_request = None
    if shop.has_items_with_runes():
        weapon_to_armor_proportion = shop.item_with_runes_shop_info.weapon_to_armor_proportion
        weapons = int(shop_request.number * weapon_to_armor_proportion)
        armor = int(shop_request.number * (1 - weapon_to_armor_proportion))

        item_with_runes_search_request = ItemWithRunesSearchRequest(
            level_request=LevelRequest(weights),
            weapons=weapons,
            armor=armor
        )

    return GeneralSearchRequest(equipment_search_request, item_with_runes_search_request)


def _display_as_table_str(items: list[AonItemJson]):
    fields = ['name', 'rarity', 'level', 'source', 'price_raw', 'url']
    return _to_table_str(items, fields)


def _generate_shop_item_weights(shop_level, max_level=30, decay=0.5) -> dict[int, float]:
    weights = {}

    for level in range(max_level + 1):
        if level <= shop_level:
            weights[level] = math.exp((-1) * decay * (shop_level - level))
        elif level == shop_level + 1:
            weights[level] = 0.2
        elif level == shop_level + 2:
            weights[level] = 0.05

    return weights


def _to_table_str(items: list[AonItemJson], keys: list[str]) -> str:
    data = [{key: getattr(item, key, "") for key in keys} for item in items]
    df = pd.DataFrame(data, columns=keys)
    return df.to_string(index=False)


if __name__ == '__main__':
    main()
