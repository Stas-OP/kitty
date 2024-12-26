from dataclasses import dataclass
from environs import Env
from datetime import datetime, time

@dataclass
class Config:
    token: str
    timezone: str = 'Asia/Novosibirsk'
    night_start: time = time(22, 0)  # 22:00
    night_end: time = time(6, 0)     # 06:00
    stats_decrease_hours: int = 6     # Уменьшение характеристик каждые 6 часов
    connection_code_ttl: int = 24     # Время жизни кода подключения в часах

def load_config(path: str = None) -> Config:
    env = Env()
    env.read_env(path)
    
    return Config(
        token=env.str('BOT_TOKEN')
    ) 