import random
import re
from abc import abstractmethod, ABC
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from aon_item_loader import AonItemJson, AonItemLoader


@dataclass
class ItemOutputData:
    name: str
    rarity: str
    level: int
    price_raw: str
    url: str = ''
    markdown: str | None = None


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
    equipment_search_request: EquipmentSearchRequest | None
    item_with_runes_search_request: ItemWithRunesSearchRequest | None


@dataclass(frozen=True)
class _ItemWithRunes:
    item: AonItemJson
    potency: AonItemJson | None
    strength: AonItemJson | None
    item_type_data: ItemTypeData
    property_runes: list[AonItemJson] = field(default_factory=list)

    def __get_all_as_list(self) -> list[AonItemJson]:
        l = [self.item, self.potency, self.strength, *self.property_runes]
        return [item for item in l if item is not None]

    def get_gp_cost(self) -> str:
        # Ex: '100 gp, 10 sp, 1 cp' or '100 gp', etc
        cost = sum([_get_cost_in_cp(item.price_raw) for item in self.__get_all_as_list()])
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
        return (_get_item_potency_by_name(self.potency.name) + ' ') if self.potency else ''

    def get_strength_modifier_str(self) -> str:
        return (_get_item_strength_by_name(self.strength.name,
                                           self.item_type_data.strength_name) + ' ') if self.strength else ''

    def get_property_runes_str(self) -> str:
        properties_str = ' '.join([item.name for item in self.property_runes])
        return f'{properties_str} ' if properties_str != '' else ''

    def get_name(self) -> str:
        return f'{self.get_potency_modifier_str()}{self.get_strength_modifier_str()}{self.get_property_runes_str()}{self.item.name}'


@dataclass(frozen=True)
class RunesInfo:
    item_potency_level_to_item: dict[int, list[AonItemJson]]
    item_strength_level_to_item: dict[int, list[AonItemJson]]
    item_property_runes_level_to_items: dict[int, list[AonItemJson]]
    items: list[AonItemJson]
    item_type_data: ItemTypeData


class ISearchService(ABC):
    @abstractmethod
    def get_random_items_by_request(self, general_search_request: GeneralSearchRequest) -> list[ItemOutputData]:
        pass


def _to_item_output_data(item: AonItemJson) -> ItemOutputData:
    return ItemOutputData(
        name=item.name,
        rarity=item.rarity,
        level=item.level,
        price_raw=item.price_raw,
        url=item.url,
        markdown=item.markdown
    )


def _find_names_in_markdown(markdown: str) -> list[str]:
    markdown = markdown.replace('\n', '')
    markdown = markdown.replace('\r', '')
    regex = r'<title[\s\S]*?right="Item\s\d+"[\s\S]*?>(.*?)<\/title>'
    match = re.search(regex, markdown)
    if match is None:
        return []
    return list(map(str.strip, match.groups()))


def _parse_aon_price(aon_item_json: ItemOutputData) -> str:
    if aon_item_json.price_raw != '':
        return aon_item_json.price_raw

    regex = r"\*\*Price\*\* (\d+ gp)(?: (\d+sp))?(?: (\d+cp))?"
    match = re.search(regex, aon_item_json.markdown)
    if match is None:
        return ''

    markdown_names = _find_names_in_markdown(aon_item_json.markdown)

    for i in range(len(markdown_names)):
        if markdown_names[i] in aon_item_json.name:
            return match.group(i)

    return match.group(0)


def _fix_aon_price(items: list[ItemOutputData]) -> None:
    for item in items:
        if item.markdown is not None:
            price = _parse_aon_price(item)
            if 'Price' in price:
                price = ' '.join(price.split(' ')[1:])
            item.price_raw = price


def first(flter: Callable[[any], bool], iterable: list[any]) -> any:
    return next(item for item in iterable if flter(item))


@dataclass(frozen=True)
class AonSearchService(ISearchService):
    aon_item_loader: AonItemLoader
    sources: list[str]

    def get_random_items_by_request(self, general_search_request: GeneralSearchRequest) -> list[ItemOutputData]:
        result = []
        if general_search_request.equipment_search_request is not None:
            result.extend(self._get_random_equipment(general_search_request.equipment_search_request))

        if general_search_request.item_with_runes_search_request is not None:
            result.extend(
                self._generate_weapon_runes_based_on_request(general_search_request.item_with_runes_search_request))
            result.extend(
                self._generate_armor_runes_based_on_request(general_search_request.item_with_runes_search_request))

        _fix_aon_price(result)
        return result

    def _get_random_equipment(self, search_request: EquipmentSearchRequest) -> list[ItemOutputData]:
        equipment = self.aon_item_loader.load_items_by_categories(search_request.traits.categories)
        items = [item for item in equipment if _any_from_list_is_in_list(item.source, self.sources)]
        items = [item for item in items if
                 len(search_request.traits.required_traits) == 0 or _any_from_list_is_in_list(
                     item.trait, search_request.traits.required_traits)]
        items = [item for item in items if
                 not _any_from_list_is_in_list(item.trait, search_request.traits.exclude_traits)]

        for item in items:
            item.url = f"https://2e.aonprd.com{item.url}"

        items = _choose_items_by_level_and_rarity(items, search_request)
        return [_to_item_output_data(item) for item in items if item is not None]

    def _get_runes_info(self, item_type_data: ItemTypeData) -> RunesInfo:
        equipment = self.aon_item_loader.load_items_by_category('equipment')
        weapons = self.aon_item_loader.load_items_by_category(item_type_data.potency_name.lower())

        potency_postfixes = [f'{item_type_data.potency_name} Potency (+{i})' for i in range(1, 4)]

        get_striking_name_by_rank = lambda \
            postfix: f'{item_type_data.strength_name}{f' ({postfix})' if postfix is not None else ''}'
        rank_postfix = [None, 'Greater', 'Major']
        strength_postfixes = list(map(get_striking_name_by_rank, rank_postfix))


        item_potency = [first(lambda item: item.name == postfix, equipment) for postfix in potency_postfixes]
        item_strength = [first(lambda item: item.name == postfix, equipment) for postfix in strength_postfixes]

        item_potency_level_to_item: dict[int, list[AonItemJson]] = {0: []}
        for item in item_potency:
            item_potency_level_to_item[item.level] = [item]

        item_striking_level_to_item: dict[int, list[AonItemJson]] = {0: []}
        for item in item_strength:
            item_striking_level_to_item[item.level] = [item]

        item_property_runes = [item for item in equipment if
                               item.item_subcategory == f'{item_type_data.potency_name} Property Runes']

        item_property_runes_level_to_items: dict[int, list[AonItemJson]] = defaultdict(list)
        item_property_runes_level_to_items[0].append(None)

        for item in item_property_runes:
            item_property_runes_level_to_items[item.level].append(item)

        return RunesInfo(
            item_potency_level_to_item,
            item_striking_level_to_item,
            item_property_runes_level_to_items,
            weapons,
            item_type_data
        )

    def _generate_items_with_runes(
        self,
        item_type_data: ItemTypeData,
        search_request: ItemWithRunesSearchRequest
    ) -> list[ItemOutputData]:
        runes_info = self._get_runes_info(item_type_data)
        return [_get_random_item_with_runes(runes_info, search_request) for _ in range(item_type_data.amount)]

    def _generate_armor_runes_based_on_request(self, search_request: ItemWithRunesSearchRequest) -> list[
        ItemOutputData]:
        return self._generate_items_with_runes(
            ItemTypeData('Armor', 'Resilient', search_request.armor),
            search_request
        )

    def _generate_weapon_runes_based_on_request(self, search_request: ItemWithRunesSearchRequest) -> list[
        ItemOutputData]:
        return self._generate_items_with_runes(
            ItemTypeData('Weapon', 'Striking', search_request.weapons),
            search_request
        )


def _get_random_item_with_runes(runes_info: RunesInfo, search_request: ItemWithRunesSearchRequest) -> ItemOutputData:
    item_potency_rune = _get_random_item(runes_info.item_potency_level_to_item, search_request.level_request)
    potency_rank = int(_get_item_potency_by_name(item_potency_rune.name)) if item_potency_rune is not None else 0
    item_strength_rune = _get_random_item(runes_info.item_strength_level_to_item, search_request.level_request)

    item_property_runes_i = [
        rune for _ in range(random.randrange(0, potency_rank + 1))
        if
        (rune := _get_random_item(
            runes_info.item_property_runes_level_to_items,
            search_request.level_request)) is not None
    ]

    weapon_with_runes = _ItemWithRunes(
        item=random.choice(runes_info.items),
        potency=item_potency_rune,
        strength=item_strength_rune,
        property_runes=item_property_runes_i,
        item_type_data=runes_info.item_type_data
    )

    return ItemOutputData(
        name=weapon_with_runes.get_name(),
        rarity='unique',
        level=weapon_with_runes.get_level(),
        price_raw=weapon_with_runes.get_gp_cost()
    )


def _get_random_item(
    items_by_level: dict[int, list[AonItemJson]],
    level_request: LevelRequest
) -> AonItemJson | None:
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


def _choose_items_by_level_and_rarity(
    items: list[AonItemJson],
    search_request: EquipmentSearchRequest
) -> list[AonItemJson]:
    items_by_rarity_by_level: dict[str, dict[int, list[AonItemJson]]] = defaultdict(lambda: defaultdict(list))

    for item in items:
        level = item.level
        rarity = item.rarity
        items_by_level = items_by_rarity_by_level[rarity]
        items_by_level[level].append(item)

    final_items = []

    def get_random_items(rarity: str, number: int) -> list[AonItemJson]:
        return [
            _get_random_item(items_by_rarity_by_level[rarity], search_request.level_request)
            for _ in range(number)
        ]

    final_items.extend(get_random_items('common', search_request.rarity_request.common_number))
    final_items.extend(get_random_items('uncommon', search_request.rarity_request.uncommon_number))
    final_items.extend(get_random_items('rare', search_request.rarity_request.rare_number))
    final_items.extend(get_random_items('unique', search_request.rarity_request.unique_number))

    return final_items


def _get_item_potency_by_name(name: str) -> str:
    return name.split(' ')[-1][1:3]


def _get_cost_in_cp(price: str) -> int:
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


def _get_item_strength_by_name(name: str, postfix="Striking") -> str:
    if 'Greater' in name:
        return f'Greater {postfix}'

    if 'Major' in name:
        return f'Major {postfix}'

    return postfix


def _any_from_list_is_in_list(list1: list[str], list2: list[str]) -> bool:
    return any(item in list1 for item in list2)
