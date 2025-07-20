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