import argparse
import math
from dataclasses import dataclass
from enum import Enum

import pandas as pd

from aon_item_loader import LocalFileAonItemLoader
from search_service import TraitRequest, RarityRequest, EquipmentSearchRequest, LevelRequest, \
    ItemWithRunesSearchRequest, AonSearchService, GeneralSearchRequest, ISearchService, ItemOutputData


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

    search_service: ISearchService = AonSearchService(LocalFileAonItemLoader(), sources)
    search_request = create_search_request(shop_request)
    items = search_service.get_random_items_by_request(search_request)

    fields = ['name', 'rarity', 'level', 'source', 'price_raw', 'url']

    if shop_request.html:
        print(_to_html_table_str(items, fields))

    print(_display_as_table_str(items, fields))

    if shop_request.create_shopkeeper:
        print(create_zany_shopkeeper(items))


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
    decay: float = 0.5

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
            traits_by_shop_type=TraitRequest(required_traits=['Magical'], exclude_traits=['Consumable', 'Tattoo']),
        ),
        decay=0.2
    ),
    ShopType.POISON: Shop(
        equipment_shop_info=EquipmentShopInfo(
            traits_by_shop_type=TraitRequest(required_traits=['Poison'])
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
    decay: float | None
    html: bool = False
    create_shopkeeper: bool = False


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
    parser.add_argument('--decay', type=float, help='Decay for item level', default=None)
    parser.add_argument('--number', type=int, help='Number of items for weapons and armor', default=10)

    parser.add_argument('--no_html', help='Disable html output', action=argparse.BooleanOptionalAction)
    parser.add_argument('--shopkeeper', help='Create a zany shopkeeper', action=argparse.BooleanOptionalAction)

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
        decay=args.decay,
        html=not args.no_html,
        create_shopkeeper=args.shopkeeper
    )


def create_search_request(shop_request: ShopRequest) -> GeneralSearchRequest:
    shop: Shop = shop_by_shop_type[shop_request.shop_type]
    weights = _generate_shop_item_weights(shop_request.level, decay=shop_request.decay or shop.decay)

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


def _display_as_table_str(items: list[ItemOutputData], fields: list[str]) -> str:
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


def create_zany_shopkeeper(aon_items: list[ItemOutputData]) -> str:
    import json
    json_str = json.dumps([item.__dict__ for item in aon_items])

    from openai import OpenAI
    client = OpenAI(
        # Defaults to os.environ.get("OPENAI_API_KEY")
    )

    message = "Create 3 zany shopkeepers who may sell the following items. Items are in json format. Just tell me their names, ancestry, personalities, and character quirks, as well as why they might have these items.:\n\n" + json_str
    chat_completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": message}]
    )

    return chat_completion.choices[0].message.content


def _to_table_str(items: list[ItemOutputData], keys: list[str]) -> str:
    data = [{key: getattr(item, key, "") for key in keys} for item in items]
    df = pd.DataFrame(data, columns=keys)
    return df.to_string(index=False)


def _to_html_table_str(items: list[ItemOutputData], keys: list[str]) -> str:
    # Create the opening HTML table tag
    html = ['<table border="1">', '<thead><tr>']

    use_linked_name = False

    keys = keys.copy()
    if 'name' in keys and 'url' in keys:
        use_linked_name = True
        keys.remove('url')
        keys.remove('name')

    # Create the table header row
    if use_linked_name:
        html.append('<th>Name</th>')

    for key in keys:
        html.append(f'<th>{key.capitalize()}</th>')

    html.append('</tr></thead>')

    # Create the table body with rows for each item
    html.append('<tbody>')
    for item in items:
        row = '<tr>'
        if use_linked_name:
            row += f'<td><a href="{item.url}">{item.name}</a></td>'
        for key in keys:
            value = getattr(item, key, '')  # Get attribute value or empty string if missing
            row += f'<td>{value}</td>'
        row += '</tr>'
        html.append(row)
    html.append('</tbody>')

    # Close the HTML table tag
    html.append('</table>')

    return ''.join(html)


if __name__ == '__main__':
    main()
