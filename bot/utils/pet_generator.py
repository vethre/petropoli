import random

PETS_BY_RARITY = {
    "Обычная": [
        ("Собака", "Баланс"),
        ("Кошка", "Дамаг-диллер"),
        ("Хорек", "Саппорт"),
        ("Кролик", "Баланс"),
        ("Морская свинка", "Саппорт"),
        ("Курица", "Саппорт"),
    ],
    "Необычная": [
        ("Лиса", "Дамаг-диллер"),
        ("Енот", "Баланс"),
        ("Утка", "Саппорт"),
        ("Гусь", "Танк"),
        ("Белка", "Дамаг-диллер"),
        ("Волк", "Дамаг-диллер"),
    ],
    "Редкая": [
        ("Сова", "Дамаг-диллер"),
        ("Филин", "Баланс"),
        ("Рысь", "Дамаг-диллер"),
        ("Бобр", "Танк"),
        ("Олень", "Баланс"),
        ("Лань", "Саппорт"),
    ],
    "Очень Редкая": [
        ("Медведь", "Танк"),
        ("Кабан", "Танк"),
        ("Барсук", "Баланс"),
        ("Выдра", "Саппорт"),
        ("Заяц-беляк", "Саппорт"),
        ("Глухарь", "Танк"),
    ],
    "Эпическая": [
        ("Гепард", "Дамаг-диллер"),
        ("Пантера", "Дамаг-диллер"),
        ("Горилла", "Танк"),
        ("Орангутанг", "Саппорт"),
        ("Носорог", "Танк"),
        ("Бегемот", "Танк"),
    ],
    "Легендарная": [
        ("Лев", "Танк"),
        ("Тигр", "Дамаг-диллер"),
        ("Слон", "Танк"),
        ("Жираф", "Саппорт"),
        ("Королевская кобра", "Дамаг-диллер"),
        ("Крокодил", "Танк"),
    ],
    "Мифическая": [
        ("Дракон Комодо", "Танк"),
        ("Гризли", "Танк"),
        ("Бизон", "Танк"),
        ("Анаконда", "Баланс"),
        ("Оцелот", "Дамаг-диллер"),
        ("Фенек", "Саппорт"),
    ],
    "Древняя": [
        ("Мамонт", "Танк"),
        ("Саблезубый тигр", "Дамаг-диллер"),
        ("Птеродактиль", "Дамаг-диллер"),
        ("Мегалодон", "Танк"),
        ("Динозавр", "Баланс"),
        ("Лютоволк", "Дамаг-диллер"),
    ],
    "Божественная": [
        ("Феникс", "Саппорт"),
        ("Единорог", "Саппорт"),
        ("Грифон", "Баланс"),
        ("Кракен", "Танк"),
        ("Цербер", "Дамаг-диллер"),
        ("Химера", "Баланс"),
    ],
    "Абсолютная": [
        ("Йормунганд", "Танк"),
        ("Зевс-Орел", "Дамаг-диллер"),
        ("Аид-Цербер", "Танк"),
        ("Космический Кит", "Баланс"),
        ("Кицунэ", "Саппорт"),
        ("Первобытный Дракон", "Дамаг-диллер"),
    ]
}

RARITY_CHANCES = [
    ("Обычная", 40),
    ("Необычная", 20),
    ("Редкая", 12),
    ("Очень Редкая", 8),
    ("Эпическая", 6),
    ("Легендарная", 4),
    ("Мифическая", 3),
    ("Древняя", 3),
    ("Божественная", 2),
    ("Абсолютная", 2),
]

RARITY_STATS_RANGE = {
    "Обычная": (10, 25),
    "Необычная": (20, 35),
    "Редкая": (30, 45),
    "Очень Редкая": (35, 50),
    "Эпическая": (40, 60),
    "Легендарная":(45, 68),
    "Мифическая":(50, 70),
    "Древняя":(58, 78),
    "Божественная":(68, 82),
    "Абсолютная":(85, 120),
}

RARITY_TOTAL_STAT_MULTIPLIER = {
    "Обычная": 1.0,
    "Необычная": 1.2,
    "Редкая": 1.4,
    "Очень Редкая": 1.6,
    "Эпическая": 1.8,
    "Легендарная": 2.0,
    "Мифическая": 2.2,
    "Древняя": 2.5,
    "Божественная": 2.8,
    "Абсолютная": 3.5, # Absolute rarity gets a significant boost
}

RARITIES = {
    "Обычная": {"min_stats": (5, 5, 20), "max_stats": (10, 10, 30), "coin_rate_range": (1, 3)},
    "Необычная": {"min_stats": (8, 8, 25), "max_stats": (15, 15, 40), "coin_rate_range": (2, 5)},
    "Редкая": {"min_stats": (12, 12, 30), "max_stats": (20, 20, 50), "coin_rate_range": (4, 8)},
    "Очень Редкая": {"min_stats": (18, 18, 40), "max_stats": (28, 28, 65), "coin_rate_range": (6, 12)},
    "Эпическая": {"min_stats": (25, 25, 50), "max_stats": (38, 38, 80), "coin_rate_range": (10, 18)},
    "Легендарная": {"min_stats": (35, 35, 60), "max_stats": (50, 50, 100), "coin_rate_range": (15, 25)},
    "Древняя": {"min_stats": (45, 45, 70), "max_stats": (65, 65, 120), "coin_rate_range": (20, 35)},
    "Мифическая": {"min_stats": (60, 60, 85), "max_stats": (80, 80, 150), "coin_rate_range": (30, 50)},
    "Божественная": {"min_stats": (75, 75, 100), "max_stats": (95, 95, 180), "coin_rate_range": (45, 70)},
    "Абсолютная": {"min_stats": (90, 90, 120), "max_stats": (120, 120, 200), "coin_rate_range": (60, 100)},
}

# Egg Definitions (из вашего кода, но с добавлением name_ru для удобства вывода)
EGG_TYPES = {
    "базовое": {
        "name_ru": "Базовое яйцо",
        "cost": 100,
        "rarities": ["Обычная", "Необычная"],
        "description": "Простое яйцо с обычными питомцами.",
        "rarity_probs": { # Вероятности для этого яйца
            "Обычная": 0.7,
            "Необычная": 0.3,
        }
    },
    "всмятку": {
        "name_ru": "Яйцо Всмятку",
        "cost": 500,
        "rarities": ["Редкая", "Очень Редкая"],
        "description": "Яйцо с более редкими питомцами.",
        "rarity_probs": {
            "Редкая": 0.6,
            "Очень Редкая": 0.4,
        }
    },
    "крутое": {
        "name_ru": "Крутое яйцо",
        "cost": 2500,
        "rarities": ["Эпическая", "Легендарная"],
        "description": "Яйцо, из которого могут вылупиться очень сильные питомцы.",
        "rarity_probs": {
            "Эпическая": 0.7,
            "Легендарная": 0.3,
        }
    },
    "дореволюционное": {
        "name_ru": "Дореволюционное яйцо",
        "cost": None, # Не продается за монеты, только за активности
        "rarities": ["Древняя", "Мифическая"],
        "description": "Очень старое яйцо. Можно найти в глубинах данжей.",
        "rarity_probs": {
            "Древняя": 0.6,
            "Мифическая": 0.4,
        }
    },
    "фаберже": {
        "name_ru": "Яйцо Фаберже",
        "cost": None, # Не продается за монеты, только за активности
        "rarities": ["Божественная", "Абсолютная"],
        "description": "Легендарное яйцо, говорят, содержит самых могущественных питомцев. Добывается только в самых сложных испытаниях.",
        "rarity_probs": {
            "Божественная": 0.5,
            "Абсолютная": 0.5,
        }
    }
}

# PET_CLASSES (если это константы, лучше держать их тут)
PET_CLASSES = ["Баланс", "Дамаг-диллер", "Саппорт", "Танк"]

def get_random_rarity_from_egg(egg_type: str, egg_types_config: dict) -> str:
    """Выбирает случайную редкость на основе вероятностей для данного типа яйца."""
    rarities_info = egg_types_config.get(egg_type)
    if not rarities_info:
        return None # Или поднять ошибку

    rarity_probs = rarities_info["rarity_probs"]
    
    rarity_choices = list(rarity_probs.keys())
    probabilities = list(rarity_probs.values())
    
    return random.choices(rarity_choices, weights=probabilities, k=1)[0]


def generate_stats_for_class(pclass: str, rarity: str, rarity_stats_range: dict, rarity_total_stat_multiplier: dict) -> dict:
    # Ваша существующая функция generate_stats_for_class, но принимает словари как аргументы
    min_base_stat, max_base_stat = rarity_stats_range[rarity]
    base_total_points = (min_base_stat + max_base_stat) / 2 * 3 
    total_points = int(base_total_points * rarity_total_stat_multiplier[rarity])

    total_points = random.randint(max(total_points - 10, min_base_stat * 3), total_points + 10)
    
    min_per_stat = int(min_base_stat * 0.5)
    min_per_stat = max(5, min_per_stat) 

    # Distribution based on class
    if pclass == "Дамаг-диллер":
        atk_weight = random.uniform(0.45, 0.55)
        hp_weight = random.uniform(0.25, 0.35)
        def_weight = 1.0 - atk_weight - hp_weight
        
        atk = int(total_points * atk_weight)
        hp = int(total_points * hp_weight)
        defense = total_points - atk - hp

    elif pclass == "Саппорт":
        def_weight = random.uniform(0.45, 0.55)
        hp_weight = random.uniform(0.25, 0.35)
        atk_weight = 1.0 - def_weight - hp_weight

        defense = int(total_points * def_weight)
        hp = int(total_points * hp_weight)
        atk = total_points - defense - hp

    elif pclass == "Танк":
        hp_weight = random.uniform(0.45, 0.55)
        def_weight = random.uniform(0.25, 0.35)
        atk_weight = 1.0 - hp_weight - def_weight

        hp = int(total_points * hp_weight)
        defense = int(total_points * def_weight)
        atk = total_points - hp - defense

    else: # Баланс
        remaining_points = total_points - (min_per_stat * 3)
        
        remaining_points = max(0, remaining_points) 

        p1 = random.randint(0, remaining_points)
        p2 = random.randint(0, remaining_points - p1)
        p3 = remaining_points - p1 - p2

        parts = [p1, p2, p3]
        random.shuffle(parts)
        
        atk = min_per_stat + parts[0]
        defense = min_per_stat + parts[1]
        hp = min_per_stat + parts[2]

    atk = max(min_per_stat, atk) 
    defense = max(min_per_stat, defense)
    hp = max(min_per_stat, hp)

    return {"atk": atk, "def": defense, "hp": hp}


def roll_pet_from_egg_type(egg_type: str, pets_by_rarity: dict, egg_types_config: dict) -> dict:
    """Выбирает случайного питомца и его редкость на основе типа яйца."""
    selected_rarity = get_random_rarity_from_egg(egg_type, egg_types_config)
    
    if not selected_rarity:
        return None

    name, pclass = random.choice(pets_by_rarity[selected_rarity])
    return {
        "name": name,
        "rarity": selected_rarity,
        "class": pclass
    }
