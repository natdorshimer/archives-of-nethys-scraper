import random
from collections import defaultdict
from dataclasses import dataclass, field

from aon_util import AonItemJson, load_items_by_category, load_items_by_categories

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


@dataclass(frozen=True)
class ItemOutputData:
    name: str
    rarity: str
    level: int
    price_raw: str
    url: str = ''


@dataclass(frozen=True)
class ItemTypeData:
    potency_name: str
    strength_name: str
    amount: int


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
class EquipmentSearchRequest:
    rarity_request: RarityRequest
    traits: TraitRequest
    level_request: LevelRequest


@dataclass(frozen=True)
class ItemWithRunesSearchRequest:
    level_request: LevelRequest
    weapons: int
    armor: int


@dataclass(frozen=True)
class GeneralSearchRequest:
    equipment_search_request: EquipmentSearchRequest
    item_with_runes_search_request: ItemWithRunesSearchRequest


def get_random_items_by_request(search_request: EquipmentSearchRequest | ItemWithRunesSearchRequest) -> list[
                                                                                                            ItemOutputData] | \
                                                                                                        list[
                                                                                                            AonItemJson]:
    if isinstance(search_request, EquipmentSearchRequest):
        return get_random_equipment(search_request)

    result = []
    result.extend(generate_weapon_runes_based_on_request(search_request))
    result.extend(generate_armor_runes_based_on_request(search_request))
    return result


def get_item_potency_by_name(name: str) -> str:
    return name.split(' ')[-1][1:3]


def get_item_strength_by_name(name: str, postfix="Striking") -> str:
    if 'Greater' in name:
        return f'Greater {postfix}'

    if 'Major' in name:
        return f'Major {postfix}'

    return postfix


def get_cost_in_cp(price: str) -> int:
    mappings = {
        'cp': 1,
        'sp': 10,
        'gp': 100
    }
    # Format: '100 gp, 10 sp, 1 cp' or '100 gp', etc
    if price == '':
        return 0
    price_split = price.split(', ')
    return sum([int(price_split[i].split(' ')[0].replace(',', '')) * mappings[price_split[i].split(' ')[1]] for i in
                range(len(price_split))])


@dataclass(frozen=True)
class ItemWithRunes:
    weapon: AonItemJson
    potency: AonItemJson | None
    strength: AonItemJson | None
    item_type_data: ItemTypeData
    property_runes: list[AonItemJson] = field(default_factory=list)

    def __get_all_as_list(self) -> list[AonItemJson]:
        l = [self.weapon, self.potency, self.strength, *self.property_runes]
        return [item for item in l if item is not None]

    def get_gp_cost(self) -> str:
        # Ex: '100 gp, 10 sp, 1 cp' or '100 gp', etc
        cost = sum([get_cost_in_cp(item.price_raw) for item in self.__get_all_as_list()])
        gp_cost = int(cost / 100)
        sp_cost = int((cost % 100) / 10)
        cp_cost = cost % 10
        cost = f'{gp_cost} gp'
        if sp_cost > 0:
            cost += f', {sp_cost} sp'
        if cp_cost > 0:
            cost += f', {cp_cost} cp'
        return cost

    def get_level(self) -> int:
        return max([item.level if item is not None else 0 for item in self.__get_all_as_list()])

    def get_potency_modifier_str(self) -> str:
        return (get_item_potency_by_name(self.potency.name) + ' ') if self.potency else ''

    def get_strength_modifier_str(self) -> str:
        return (get_item_strength_by_name(self.strength.name,
                                          self.item_type_data.strength_name) + ' ') if self.strength else ''

    def get_property_runes_str(self) -> str:
        properties_str = ' '.join([item.name for item in self.property_runes])
        return f'{properties_str} ' if properties_str != '' else ''

    def get_name(self) -> str:
        return f'{self.get_potency_modifier_str()}{self.get_strength_modifier_str()}{self.get_property_runes_str()}{self.weapon.name}'


def any_from_list_is_in_list(list1: list[str], list2: list[str]) -> bool:
    return any(item in list1 for item in list2)


def get_random_equipment(search_request: EquipmentSearchRequest) -> list[AonItemJson]:
    equipment = load_items_by_categories(search_request.traits.categories)
    items = [item for item in equipment if any_from_list_is_in_list(item.source, sources)]
    items = [item for item in items if
             len(search_request.traits.required_traits) == 0 or any_from_list_is_in_list(
                 item.trait, search_request.traits.required_traits)]
    items = [item for item in items if not any_from_list_is_in_list(item.trait, search_request.traits.exclude_traits)]

    for item in items:
        item.url = f"https://2e.aonprd.com{item.url}"

    return choose_items_by_level_and_rarity(items, search_request)


def get_random_item(items_by_level: dict[int, list[AonItemJson]], level_request: LevelRequest) -> AonItemJson | None:
    level_to_weight = level_request.weights.copy()
    for weight in level_request.weights:
        if weight not in items_by_level:
            level_to_weight.pop(weight)

    if len(level_to_weight) == 0 or len(items_by_level) == 0:
        return None

    levels_to_choose = list(level_to_weight.keys())
    weights = list(level_to_weight.values())
    level = random.choices(levels_to_choose, weights=weights)[0]
    items_to_choose = items_by_level[level]
    return random.choice(items_to_choose) if len(items_to_choose) > 0 else None


def choose_items_by_level_and_rarity(items: list[AonItemJson], search_request: EquipmentSearchRequest) -> list[
    AonItemJson]:
    items_by_rarity_by_level: dict[str, dict[int, list[AonItemJson]]] = defaultdict(lambda: defaultdict(list))

    for item in items:
        level = item.level
        rarity = item.rarity
        items_by_level = items_by_rarity_by_level[rarity]
        items_by_level[level].append(item)

    final_items = []

    def get_random_items(rarity: str, number: int) -> list[AonItemJson]:
        return [
            get_random_item(items_by_rarity_by_level[rarity], search_request.level_request)
            for _ in range(number)
        ]

    final_items.extend(get_random_items('common', search_request.rarity_request.common_number))
    final_items.extend(get_random_items('uncommon', search_request.rarity_request.uncommon_number))
    final_items.extend(get_random_items('rare', search_request.rarity_request.rare_number))
    final_items.extend(get_random_items('unique', search_request.rarity_request.unique_number))

    return final_items


def generate_items_with_runes(search_request: ItemWithRunesSearchRequest, item_type_data: ItemTypeData) -> list[
    ItemOutputData]:
    equipment = load_items_by_category('equipment')
    weapons = load_items_by_category(item_type_data.potency_name.lower())

    item_potency = {
        1: next(filter(lambda item: item.name == f'{item_type_data.potency_name} Potency (+1)', equipment)),
        2: next(filter(lambda item: item.name == f'{item_type_data.potency_name} Potency (+2)', equipment)),
        3: next(filter(lambda item: item.name == f'{item_type_data.potency_name} Potency (+3)', equipment))
    }

    item_strength = {
        1: next(filter(lambda item: item.name == f'{item_type_data.strength_name}', equipment)),
        2: next(filter(lambda item: item.name == f'{item_type_data.strength_name} (Greater)', equipment)),
        3: next(filter(lambda item: item.name == f'{item_type_data.strength_name} (Major)', equipment))
    }

    item_potency_level_to_item: dict[int, list[AonItemJson]] = {0: []}
    for item in item_potency.values():
        item_potency_level_to_item[item.level] = [item]

    item_striking_level_to_item: dict[int, list[AonItemJson]] = {0: []}
    for item in item_strength.values():
        item_striking_level_to_item[item.level] = [item]

    item_property_runes = [item for item in equipment if
                           item.item_subcategory == f'{item_type_data.potency_name} Property Runes']

    item_property_runes_level_to_items: dict[int, list[AonItemJson]] = defaultdict(list)
    item_property_runes_level_to_items[0].append(None)

    for item in item_property_runes:
        item_property_runes_level_to_items[item.level].append(item)

    def generate_item_with_runes() -> ItemOutputData:
        item_potency_rune = get_random_item(item_potency_level_to_item, search_request.level_request)
        potency_rank = int(get_item_potency_by_name(item_potency_rune.name)) if item_potency_rune is not None else 0
        item_strength_rune = get_random_item(item_striking_level_to_item, search_request.level_request)

        item_property_runes_i = [
            rune for _ in range(random.randrange(0, potency_rank + 1))
            if (rune := get_random_item(item_property_runes_level_to_items, search_request.level_request)) is not None
        ]

        weapon_with_runes = ItemWithRunes(
            weapon=random.choice(weapons),
            potency=item_potency_rune,
            strength=item_strength_rune,
            property_runes=item_property_runes_i,
            item_type_data=item_type_data
        )
        return ItemOutputData(
            name=weapon_with_runes.get_name(),
            rarity='unique',
            level=weapon_with_runes.get_level(),
            price_raw=weapon_with_runes.get_gp_cost()
        )

    return [generate_item_with_runes() for _ in range(item_type_data.amount)]


def generate_armor_runes_based_on_request(search_request: ItemWithRunesSearchRequest) -> list[ItemOutputData]:
    return generate_items_with_runes(search_request, ItemTypeData('Armor', 'Resilient', search_request.armor))


def generate_weapon_runes_based_on_request(search_request: ItemWithRunesSearchRequest) -> list[ItemOutputData]:
    return generate_items_with_runes(search_request, ItemTypeData('Weapon', 'Striking', search_request.weapons))
