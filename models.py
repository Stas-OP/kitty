from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Optional, List, Dict
import json
import os

@dataclass
class Cat:
    owner_id: int
    name: str
    color: str
    hunger: int = 4
    happiness: int = 4
    energy: int = 4
    created_at: datetime = field(default_factory=datetime.now)
    walk_time: Optional[str] = None
    connected_users: List[int] = field(default_factory=list)
    last_messages: Dict[int, datetime] = field(default_factory=dict)
    
    @property
    def age_days(self) -> int:
        return (datetime.now() - self.created_at).days + 1

    def to_dict(self) -> dict:
        return {
            'owner_id': self.owner_id,
            'name': self.name,
            'color': self.color,
            'hunger': self.hunger,
            'happiness': self.happiness,
            'energy': self.energy,
            'created_at': self.created_at.isoformat(),
            'walk_time': self.walk_time,
            'connected_users': self.connected_users,
            'last_messages': {
                str(user_id): date.isoformat() if isinstance(date, datetime) else date
                for user_id, date in self.last_messages.items()
            }
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Cat':
        data = data.copy()
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'last_messages' in data:
            data['last_messages'] = {
                int(user_id): datetime.fromisoformat(date) if isinstance(date, str) else date
                for user_id, date in data['last_messages'].items()
            }
        return cls(**data)

class Storage:
    def __init__(self, file_path: str = 'data.json'):
        self.file_path = file_path
        self.cats: Dict[int, Cat] = {}
        self.connection_codes: Dict[str, tuple[int, datetime]] = {}
        self.load()
    
    def load(self):
        if not os.path.exists(self.file_path):
            self.cats = {}
            self.connection_codes = {}
            return
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.cats = {
                int(owner_id): Cat.from_dict(cat_data) 
                for owner_id, cat_data in data.get('cats', {}).items()
            }
            
            # Загружаем коды подключения, преобразуя строки дат обратно в datetime
            self.connection_codes = {
                code: (int(owner_id), datetime.fromisoformat(expires))
                for code, (owner_id, expires) in data.get('connection_codes', {}).items()
            }
            
        except json.JSONDecodeError:
            print("Ошибка чте��ия JSON файла!")
            # Создаём резервную копию файла
            backup_name = f"{self.file_path}.backup"
            try:
                import shutil
                shutil.copy2(self.file_path, backup_name)
                print(f"Создана резервная копия данных: {backup_name}")
            except Exception as e:
                print(f"Ошибка при создании резервной копии: {e}")
            
            # Не очищаем данные, оставляем как есть
            if not hasattr(self, 'cats'):
                self.cats = {}
            if not hasattr(self, 'connection_codes'):
                self.connection_codes = {}
            
        except Exception as e:
            print(f"Неожиданная ошибка при загрузке данных: {e}")
            # Также не очищаем существующие данные
            if not hasattr(self, 'cats'):
                self.cats = {}
            if not hasattr(self, 'connection_codes'):
                self.connection_codes = {}
    
    def save(self):
        data = {
            'cats': {
                str(owner_id): cat.to_dict()
                for owner_id, cat in self.cats.items()
            },
            'connection_codes': {
                code: (owner_id, expires.isoformat())
                for code, (owner_id, expires) in self.connection_codes.items()
                if isinstance(expires, datetime)  # Проверяем, что expires это datetime
            }
        }
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2) 