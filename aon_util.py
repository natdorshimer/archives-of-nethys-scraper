import json
from dataclasses import dataclass, field

from dacite import from_dict


@dataclass
class AonItemJson:
    name: str
    rarity: str
    level: int
    url: str
    category: str
    id: str = ''
    price_raw: str = ''
    source: list[str] = field(default_factory=list)
    trait: list[str] = field(default_factory=list)
    item_subcategory: str = ''

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other) -> bool:
        return self.id == other.id


def load_items_by_category(category: str) -> list[AonItemJson]:
    with open(f'aon-data/aon39/{category}.json') as f:
        equipment = json.load(f)
        return [from_dict(AonItemJson, item) for item in equipment]


def load_items_by_categories(categories: list[str]) -> list[AonItemJson]:
    items = []
    for category in categories:
        items.extend(load_items_by_category(category))
    return items
