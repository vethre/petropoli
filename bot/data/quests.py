# bot/data/quests.py

QUESTS_DEFINITIONS = {
    # --- Начальные квесты (Tier 1) ---
    "first_egg_collection": {
        "name": "Первое яйцо",
        "description": "Собери свое первое яйцо.",
        "type": "collect_eggs",
        "goal": 1,
        "reward_coins": 100,
        "reward_egg_type": None,
        "prerequisite_quest": None,
        "zone": None # Не привязан к конкретной зоне
    },
    "hatch_first_pet": {
        "name": "Первое рождение",
        "description": "Вылупи своего первого питомца из яйца.",
        "type": "hatch_pets",
        "goal": 1,
        "reward_coins": 150,
        "reward_egg_type": "обычное", # Пример: обычное яйцо
        "prerequisite_quest": "first_egg_collection",
        "zone": None
    },
    "explore_meadow_3_times": {
        "name": "Исследователь Лужайки I",
        "description": "Исследуй Лужайку 3 раза.",
        "type": "explore_zone",
        "zone_target": "Лужайка",
        "goal": 3,
        "reward_coins": 100,
        "reward_egg_type": None,
        "prerequisite_quest": "hatch_first_pet",
        "zone": "Лужайка"
    },
    "collect_500_coins": {
        "name": "Богач на старте",
        "description": "Собери 500 монет.",
        "type": "collect_coins", # Новый тип
        "goal": 500,
        "reward_coins": 200,
        "reward_egg_type": None,
        "prerequisite_quest": None, # Может быть доступен сразу
        "zone": None
    },
    "merge_1_pet": {
        "name": "Начинающий селекционер",
        "description": "Объедини 1 питомца (любого).",
        "type": "merge_pets",
        "goal": 1,
        "reward_coins": 250,
        "reward_egg_type": "особое", # Пример: особое яйцо
        "prerequisite_quest": "hatch_first_pet",
        "zone": None
    },

    # --- Средние квесты (Tier 2) ---
    "collect_5_eggs": {
        "name": "Коллекционер яиц I",
        "description": "Собери 5 яиц в своем инвентаре.",
        "type": "collect_eggs",
        "goal": 5,
        "reward_coins": 300,
        "reward_egg_type": None,
        "prerequisite_quest": "explore_meadow_3_times",
        "zone": None
    },
    "hatch_3_pets": {
        "name": "Селекционер I",
        "description": "Вылупи 3 питомцев из яиц.",
        "type": "hatch_pets",
        "goal": 3,
        "reward_coins": 350,
        "reward_egg_type": None,
        "prerequisite_quest": "collect_5_eggs",
        "zone": None
    },
    "explore_farm_5_times": {
        "name": "Работник Фермы I",
        "description": "Исследуй Ферму 5 раз.",
        "type": "explore_zone",
        "zone_target": "Ферма",
        "goal": 5,
        "reward_coins": 400,
        "reward_egg_type": None,
        "prerequisite_quest": "explore_meadow_3_times", # Требует знания Лужайки
        "zone": "Ферма"
    },
    "defeat_3_farm_monsters": {
        "name": "Защитник Фермы",
        "description": "Победи 3 монстров на Ферме.",
        "type": "defeat_monsters_zone",
        "zone_target": "Ферма",
        "goal": 3,
        "reward_coins": 500,
        "reward_egg_type": "крутое",
        "prerequisite_quest": "explore_farm_5_times",
        "zone": "Ферма"
    },
    "reach_pet_level_5": {
        "name": "Мастер дрессировки I",
        "description": "Доведи любого питомца до 5 уровня.",
        "type": "reach_pet_level", # Новый тип
        "goal": 5,
        "reward_coins": 600,
        "reward_egg_type": None,
        "prerequisite_quest": "hatch_3_pets",
        "zone": None
    },
    "collect_1000_coins": {
        "name": "Настоящий капиталист",
        "description": "Собери 1000 монет.",
        "type": "collect_coins",
        "goal": 1000,
        "reward_coins": 750,
        "reward_egg_type": None,
        "prerequisite_quest": "collect_500_coins",
        "zone": None
    },

    # --- Продвинутые квесты (Tier 3) ---
    "explore_mountain_7_times": {
        "name": "Покоритель Горы",
        "description": "Исследуй Гору 7 раз.",
        "type": "explore_zone",
        "zone_target": "Гора",
        "goal": 7,
        "reward_coins": 800,
        "reward_egg_type": None,
        "prerequisite_quest": "defeat_3_farm_monsters", # Прошел Ферму
        "zone": "Гора"
    },
    "defeat_5_mountain_monsters": {
        "name": "Охотник в Горах",
        "description": "Победи 5 монстров на Горе.",
        "type": "defeat_monsters_zone",
        "zone_target": "Гора",
        "goal": 5,
        "reward_coins": 1000,
        "reward_egg_type": "мифическое", # Пример: редкое яйцо
        "prerequisite_quest": "explore_mountain_7_times",
        "zone": "Гора"
    },
    "merge_3_pets": {
        "name": "Опытный селекционер",
        "description": "Объедини 3 питомцев.",
        "type": "merge_pets",
        "goal": 3,
        "reward_coins": 1200,
        "reward_egg_type": None,
        "prerequisite_quest": "merge_1_pet",
        "zone": None
    },
    "hatch_10_pets": {
        "name": "Массовое рождение",
        "description": "Вылупи 10 питомцев.",
        "type": "hatch_pets",
        "goal": 10,
        "reward_coins": 1500,
        "reward_egg_type": None,
        "prerequisite_quest": "hatch_3_pets",
        "zone": None
    },
    "collect_2000_coins": {
        "name": "Золотой магнат",
        "description": "Собери 2000 монет.",
        "type": "collect_coins",
        "goal": 2000,
        "reward_coins": 2000,
        "reward_egg_type": None,
        "prerequisite_quest": "collect_1000_coins",
        "zone": None
    },
    "win_3_arena_battles": {
        "name": "Арена: Первые шаги",
        "description": "Выиграй 3 битвы на Арене.",
        "type": "win_arena_battles", # Новый тип
        "goal": 3,
        "reward_coins": 700,
        "reward_egg_type": None,
        "prerequisite_quest": "reach_pet_level_5", # Должен быть сильный питомец
        "zone": None
    }
}

# Mapping quest types to user/pet fields for progress tracking
QUEST_PROGRESS_MAPPING = {
    "collect_eggs": "eggs_collected",      # Количество яиц в инвентаре пользователя
    "hatch_pets": "hatched_count",        # Общее количество вылупленных питомцев (в таблице users)
    "merge_pets": "merged_count",         # Общее количество объединенных питомцев (в таблице users)
    "explore_zone": "explore_counts",     # JSONB в users: {zone_name: count}
    "defeat_monsters_zone": "monsters_defeated_counts", # JSONB в users: {zone_name: count}
    "collect_coins": "total_coins_collected", # Новый: общее количество собранных монет за все время
    "reach_pet_level": "highest_pet_level", # Новый: максимальный уровень любого питомца пользователя
    "win_arena_battles": "arena_wins"      # Новый: количество побед на арене (в таблице arena_team)
}