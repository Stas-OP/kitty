from PIL import Image, ImageDraw, ImageFont
import os

class ImageGenerator:
    def __init__(self):
        # Путь к папке с ресурсами
        self.resources_path = "resources"
        if not os.path.exists(self.resources_path):
            os.makedirs(self.resources_path)
            
        # Путь к папке со шрифтами
        self.fonts_path = "fonts"
        if not os.path.exists(self.fonts_path):
            os.makedirs(self.fonts_path)
        
        # Пытаемся загрузить шрифт Tecmo Bowl
        try:
            self.font_path = os.path.join(self.fonts_path, 'Tecmo Bowl.ttf')
            
            if os.path.exists(self.font_path):
                # Используем разные размеры для разной иерархии текста
                self.font_title = ImageFont.truetype(self.font_path, 24)    # Для заголовка
                self.font_name = ImageFont.truetype(self.font_path, 24)     # Для имени
                self.font_stats = ImageFont.truetype(self.font_path, 24)    # Для статистики
                self.font_owner = ImageFont.truetype(self.font_path, 20)    # Для информации о хозяйке
            else:
                raise FileNotFoundError("Шрифт не найден")
            
        except:
            # Если что-то пошло не так, используем дефолтный шрифт
            default_font = ImageFont.load_default()
            self.font_title = default_font
            self.font_name = default_font
            self.font_stats = default_font
            self.font_owner = default_font

        # Словари для транслитерации
        self.colors_trans = {
            "рыжий": "RYZHIJ",
            "серый": "SERYJ",
            "белый": "BELYJ",
            "чёрный": "CHERNYJ"
        }

        self.stats_trans = {
            "Сытость": "HUNGER",
            "Счастье": "HAPPY",
            "Энергия": "ENERGY"
        }

    def transliterate_name(self, text):
        # Словарь для транслитерации имени
        trans = {'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
                'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
                'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
                'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
                'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'}
        
        return ''.join(trans.get(char.lower(), char) for char in text).upper()

    def generate_status_image(self, color, name, hunger, happiness, energy, owner_m, owner_f, age_days):
        WIDTH = 800
        HEIGHT = 800
        
        # Пытаемся загрузить изображение котика
        cat_image_path = os.path.join(self.resources_path, f"{color}_cat.png")
        if os.path.exists(cat_image_path):
            try:
                background = Image.open(cat_image_path)
                background = background.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
                image = background
            except:
                image = Image.new('RGB', (WIDTH, HEIGHT), 'white')
        else:
            image = Image.new('RGB', (WIDTH, HEIGHT), 'white')

        draw = ImageDraw.Draw(image)

        # Черный прямоугольник сверху для заголовка
        top_overlay = Image.new('RGBA', (WIDTH, 60), (0, 0, 0, 120))
        image.paste(top_overlay, (0, 0), top_overlay)

        # Черный прямоугольник снизу слева для статистики
        stats_overlay = Image.new('RGBA', (300, 300), (0, 0, 0, 120))
        image.paste(stats_overlay, (30, HEIGHT - 320), stats_overlay)

        # Используем шрифты
        title_font = self.font_title
        stats_font = self.font_stats

        # Заголовок с декоративными линиями
        title = f"котик {name.capitalize()} ({age_days} дн.)"
        title_width = title_font.getlength(title)
        x_center = (WIDTH - title_width) // 2
        
        # Золотые линии вокруг заголовка
        line_length = 80
        padding = 20
        y_title = 20  # Позиция заголовка

        # Заголовок в светло-розовом
        title_color = '#FFB6C1'  # Светло-розовый
        draw.text((x_center, y_title), title, font=title_font, fill=title_color)
        
        # Линии того же цвета
        draw.line([(x_center - line_length - padding, y_title + 10), 
                   (x_center - padding, y_title + 10)], fill=title_color, width=2)
        draw.line([(x_center + title_width + padding, y_title + 10),
                   (x_center + title_width + line_length + padding, y_title + 10)], fill=title_color, width=2)

        # Статистика
        y_position = HEIGHT - 300  # Немного подняли статистику
        stats = [
            ("СЫТОСТЬ", hunger, '#FFA07A'),  # Светлый лососевый
            ("СЧАСТЬЕ", happiness, '#98FB98'),  # Светлый зеленый
            ("ЭНЕРГИЯ", energy, '#87CEEB')  # Небесно-голубой
        ]
        
        for stat_name, stat_value, color in stats:
            # Название параметра
            draw.text((50, y_position), f">{stat_name}:", font=stats_font, fill=color)
            
            # Рисуем деления (4 прямоугольника)
            rect_width = 50
            rect_height = 25
            rect_spacing = 5
            for i in range(4):
                x = 50 + i * (rect_width + rect_spacing)
                y = y_position + 40
                if stat_value >= i + 1:
                    draw.rectangle([(x, y), (x + rect_width, y + rect_height)], fill=color)
                else:
                    draw.rectangle([(x, y), (x + rect_width, y + rect_height)], outline=color, width=2)
            
            y_position += 90

        # Сохраняем изображение
        temp_path = os.path.join(self.resources_path, "temp_status.png")
        image.save(temp_path)
        return temp_path