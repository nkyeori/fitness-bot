FROM python:3.10-slim

# Встановлюємо залежності
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо код бота
COPY . .

# Запускаємо бота
CMD ["python", "bot.py"]
