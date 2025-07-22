CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    coins INT DEFAULT 500,
    eggs JSONB DEFAULT '[]',
    streak INT DEFAULT 0,
    last_daily TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pets (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    name TEXT,
    rarity TEXT,
    class TEXT,
    level INT,
    xp INT,
    xp_needed INT,
    stats JSONB,
    coin_rate INT,
    last_collected TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS quests (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    zone TEXT,
    name TEXT,
    description TEXT,
    progress INT DEFAULT 0,
    goal INT,
    reward_coins INT DEFAULT 0,
    reward_egg BOOLEAN DEFAULT FALSE,
    completed BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS zones (
    id SERIAL PRIMARY KEY,
    name TEXT,
    description TEXT,
    cost INT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS user_zones (
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    zone TEXT,
    unlocked BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (user_id, zone)
);

CREATE TABLE IF NOT EXISTS arena_team (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    pet_ids JSONB NOT NULL,
    wins INT DEFAULT 0,
    losses INT DEFAULT 0,
    current_rank TEXT DEFAULT 'Новичок'
);

CREATE TABLE IF NOT EXISTS monsters (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    level INTEGER NOT NULL,
    hp INTEGER NOT NULL,
    atk INTEGER NOT NULL,
    "def" INTEGER NOT NULL, 
    xp_reward INTEGER NOT NULL,
    coin_reward INTEGER NOT NULL,
    possible_item TEXT[], 
    zone_name TEXT NOT NULL,
    FOREIGN KEY (zone_name) REFERENCES zones(name)
);

INSERT INTO monsters (name, description, level, hp, atk, "def", xp_reward, coin_reward, possible_item, zone_name) VALUES
('Маленький слизень', 'Желеобразное существо.', 1, 30, 5, 2, 20, 10, '{}', 'Лужайка'),
('Дикий кабан', 'Опасное животное.', 5, 80, 15, 8, 50, 25, '{"Мясо"}', 'Ферма'),
('Горный тролль', 'Огромный и сильный.', 10, 150, 30, 15, 120, 60, '{"Руда", "Кость"}', 'Гора')
ON CONFLICT (name) DO NOTHING;



ALTER TABLE users
ADD COLUMN IF NOT EXISTS total_coins_collected BIGINT DEFAULT 0, -- Для квестов типа "collect_coins"
ADD COLUMN IF NOT EXISTS highest_pet_level INTEGER DEFAULT 0; -- Для квестов типа "reach_pet_level"

-- Обновления для таблицы users
ALTER TABLE users
ADD COLUMN IF NOT EXISTS energy INTEGER DEFAULT 200, -- Максимальная энергия 200, как мы установили в explore.py
ADD COLUMN IF NOT EXISTS hatched_count INTEGER DEFAULT 0, -- Общее количество вылупленных питомцев
ADD COLUMN IF NOT EXISTS merged_count INTEGER DEFAULT 0, -- Общее количество объединенных питомцев
ADD COLUMN IF NOT EXISTS eggs_collected INTEGER DEFAULT 0, -- Общее количество собранных яиц (если вы хотите отслеживать это отдельно от инвентаря)
ADD COLUMN IF NOT EXISTS explore_counts JSONB DEFAULT '{}'::jsonb, -- Количество исследований по зонам {"ZoneName": count}
ADD COLUMN IF NOT EXISTS monsters_defeated_counts JSONB DEFAULT '{}'::jsonb, -- Количество побежденных монстров по зонам/типам {"MonsterName": count}
ADD COLUMN IF NOT EXISTS total_coins_collected BIGINT DEFAULT 0, -- Общее количество собранных монет за все время
ADD COLUMN IF NOT EXISTS highest_pet_level INTEGER DEFAULT 0, -- Максимальный уровень любого питомца пользователя
ADD COLUMN IF NOT EXISTS active_zone TEXT DEFAULT 'Лужайка', -- Активная зона пользователя
ADD COLUMN IF NOT EXISTS user_items JSONB DEFAULT '{}'::jsonb; -- ПРОСТОЙ ИНВЕНТАРЬ: {"ItemName": count}

-- Обновления для таблицы pets
ALTER TABLE pets
ADD COLUMN IF NOT EXISTS current_hp INTEGER; -- Текущее здоровье питомца для битв

-- Обновления для таблицы quests
ALTER TABLE quests
ADD COLUMN IF NOT EXISTS quest_id TEXT, -- Ссылка на ключ в QUESTS_DEFINITIONS (например, 'first_egg_collection')
ADD COLUMN IF NOT EXISTS claimed BOOLEAN DEFAULT FALSE, -- Статус: награда за квест забрана
DROP COLUMN IF EXISTS reward_egg, -- Удаляем старый BOOLEAN столбец
ADD COLUMN IF NOT EXISTS reward_egg_type TEXT DEFAULT NULL; -- Новый TEXT столбец для типа яйца (например, 'обычное', 'крутое')

-- Обновления для таблицы zones
ALTER TABLE zones
ADD COLUMN IF NOT EXISTS explore_duration_min INTEGER DEFAULT 15,
ADD COLUMN IF NOT EXISTS explore_duration_max INTEGER DEFAULT 30,
ADD COLUMN IF NOT EXISTS monster_pool JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS pve_chance NUMERIC(3,2) DEFAULT 0.2, -- Шанс PvE столкновения (0.00-1.00)
ADD COLUMN IF NOT EXISTS buff_type TEXT DEFAULT 'none', -- Тип баффа зоны ('coin_rate', 'xp_rate', 'item_find_chance', 'energy_cost_buff')
ADD COLUMN IF NOT EXISTS buff_value NUMERIC(5,2) DEFAULT 0, -- Значение баффа (процент или абсолютное значение для шанса)
ADD COLUMN IF NOT EXISTS monster_pool JSONB DEFAULT '[]'::jsonb; -- Массив имен монстров, обитающих в этой зоне

UPDATE zones SET
    explore_duration_min = 15,
    explore_duration_max = 30,
    pve_chance = 0.1,
    buff_type = 'coin_rate',
    buff_value = 5,
    monster_pool = '["Маленький слизень"]'
WHERE name = 'Лужайка';

UPDATE zones SET
    explore_duration_min = 30,
    explore_duration_max = 60,
    pve_chance = 0.3,
    buff_type = 'xp_rate',
    buff_value = 10,
    monster_pool = '["Дикий кабан"]'
WHERE name = 'Ферма';

UPDATE zones SET
    explore_duration_min = 60,
    explore_duration_max = 120,
    pve_chance = 0.5,
    buff_type = 'item_find_chance',
    buff_value = 0.02, -- 2% дополнительный шанс найти предмет
    monster_pool = '["Горный тролль"]'
WHERE name = 'Гора';

-- Добавление новых зон (примеры)
INSERT INTO zones (name, description, cost, unlock_conditions, explore_duration_min, explore_duration_max, pve_chance, buff_type, buff_value, monster_pool) VALUES
('Древний Лес', 'Густой лес, хранящий старые тайны. Здесь можно найти редкие травы.', 1000, '{"merged_count": 1, "coins": 700}', 90, 180, 0.4, 'item_find_chance', 0.03, '["Лесной дух", "Паук-гигант"]'),
('Ледяные Пещеры', 'Холодные и опасные пещеры. Питомцы мерзнут, но награда велика.', 2500, '{"hatched_count": 15, "prerequisite_zone": "Гора_explored_5_times"}', 120, 240, 0.6, 'xp_rate', 15, '["Ледяной элементаль", "Снежный гоблин"]'),
('Забытый Храм', 'Таинственный храм, полный загадок и могущественных артефактов.', 5000, '{"highest_pet_level": 10, "prerequisite_quest": "defeat_5_mountain_monsters"}', 180, 300, 0.7, 'coin_rate', 20, '["Каменный страж", "Древний голем"]');

-- Добавление монстров для новых зон (примеры, если их нет в вашей таблице monsters)
INSERT INTO monsters (name, description, level, hp, atk, "def", xp_reward, coin_reward, possible_item, zone_name) VALUES
('Лесной дух', 'Дух леса, охраняющий его покой.', 7, 100, 20, 10, 70, 30, '{"Трава"}', 'Древний Лес'),
('Паук-гигант', 'Огромный паук, плетущий смертоносные сети.', 8, 120, 25, 12, 80, 40, '{"Яд"}', 'Древний Лес'),
('Ледяной элементаль', 'Существо из чистого льда.', 12, 180, 35, 20, 150, 80, '{"Лед"}', 'Ледяные Пещеры'),
('Снежный гоблин', 'Хитрый гоблин, приспособившийся к холоду.', 11, 160, 30, 18, 130, 70, '{"Шерсть"}', 'Ледяные Пещеры'),
('Каменный страж', 'Древний страж из камня.', 15, 250, 45, 25, 200, 100, '{"Обломок"}', 'Забытый Храм'),
('Древний голем', 'Могущественный голем, спящий тысячелетиями.', 18, 300, 50, 30, 250, 120, '{"Артефакт"}', 'Забытый Храм')
ON CONFLICT (name) DO NOTHING;