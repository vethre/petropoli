# bot/utils/battle_system.py
import random
import json

def calculate_damage(attacker_atk: int, defender_def: int) -> int:
    damage = max(1, attacker_atk * attacker_atk / (attacker_atk + defender_def))
    return int(damage)

def simulate_battle_dungeon(pets_data: list, monster_info: dict) -> dict:
    
    current_pets_state = [dict(p) for p in pets_data] # Копируем, чтобы изменять HP

    # Внимание: team_current_hp должен отражать только живых питомцев
    team_current_hp = sum(p['current_hp'] for p in current_pets_state if p['current_hp'] > 0)
    team_atk = sum(p['stats']['atk'] for p in current_pets_state if p['current_hp'] > 0)
    team_def = sum(p['stats']['def'] for p in current_pets_state if p['current_hp'] > 0)


    monster_hp = monster_info['hp']
    monster_atk = monster_info['atk']
    monster_def = monster_info['def']

    current_monster_hp = monster_hp

    battle_log = [f"⚡️ Началась битва! Ваша команда против <b>{monster_info['name_ru']}</b>!"]

    turns = 0
    max_turns = 100 

    while team_current_hp > 0 and current_monster_hp > 0 and turns < max_turns:
        turns += 1
        # Ход команды питомцев
        # Если атака команды 0 (все питомцы мертвы, что маловероятно, но как крайний случай)
        if team_atk <= 0:
            battle_log.append("Ваша команда не может атаковать (все питомцы без сознания или имеют 0 атаки).")
            break # Завершаем бой, команда проиграла

        team_damage = calculate_damage(team_atk, monster_def)
        current_monster_hp -= team_damage
        battle_log.append(f"Ход {turns}: Ваша команда атакует <b>{monster_info['name_ru']}</b>, нанося {team_damage} урона. У <b>{monster_info['name_ru']}</b> осталось {max(0, current_monster_hp)} HP.")
        
        if current_monster_hp <= 0:
            battle_log.append(f"✅ Ваша команда победила <b>{monster_info['name_ru']}</b>!")
            return {
                "victory": True,
                "xp_gained": monster_info['xp_reward'],
                "coins_gained": monster_info['coin_reward'],
                "updated_pets_data": current_pets_state, 
                "battle_log": battle_log
            }
        
        # Ход монстра
        # Если защита команды 0 (все питомцы мертвы, что маловероятно)
        if team_def <= 0:
             battle_log.append("Ваша команда не может защищаться (все питомцы без сознания или имеют 0 защиты).")
             break # Завершаем бой, команда проиграла

        monster_damage = calculate_damage(monster_atk, team_def)
        # Урон распределяется только по живым питомцам
        total_live_pets_hp_before_damage = sum(p['current_hp'] for p in current_pets_state if p['current_hp'] > 0)
        
        if total_live_pets_hp_before_damage > 0:
            for pet in current_pets_state:
                if pet['current_hp'] > 0:
                    damage_to_pet = int(monster_damage * (pet['current_hp'] / total_live_pets_hp_before_damage))
                    pet['current_hp'] -= damage_to_pet
                    if pet['current_hp'] < 0:
                        pet['current_hp'] = 0 
            
            # Обновляем общее HP команды после нанесения урона
            team_current_hp = sum(p['current_hp'] for p in current_pets_state if p['current_hp'] > 0)

            damaged_pets_log = ", ".join([f"{p['name']}: {max(0, p['current_hp'])} HP" for p in current_pets_state if p['current_hp'] > 0])
            if not damaged_pets_log: # Все питомцы мертвы
                 damaged_pets_log = "Все питомцы потеряли сознание."
            battle_log.append(f"Ход {turns}: <b>{monster_info['name_ru']}</b> атакует, нанося {monster_damage} урона команде. Состояние команды: {damaged_pets_log}.")
        else:
            battle_log.append(f"Ход {turns}: <b>{monster_info['name_ru']}</b> атакует, но все питомцы уже без сознания.")
            team_current_hp = 0 # Все питомцы мертвы

    # Если бой закончился по лимиту ходов или HP команды <= 0
    if team_current_hp <= 0:
        battle_log.append(f"❌ Ваша команда потерпела поражение от <b>{monster_info['name_ru']}</b>.")
        return {
            "victory": False,
            "xp_gained": 0,
            "coins_gained": 0,
            "updated_pets_data": current_pets_state,
            "battle_log": battle_log
        }
    else: # Монстр не был побежден за max_turns (редко, но возможно)
        battle_log.append(f"🤝 Бой с <b>{monster_info['name_ru']}</b> закончился ничьей (лимит ходов).")
        return {
            "victory": False, # Или True, если хотите считать ничью победой
            "xp_gained": 0,
            "coins_gained": 0,
            "updated_pets_data": current_pets_state,
            "battle_log": battle_log
        }