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