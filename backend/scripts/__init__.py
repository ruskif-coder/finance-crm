# Пакет нужен ради способа запуска: `python -m scripts.<имя>` кладёт /app в sys.path,
# и `from app.database import ...` внутри скрипта разрешается. Прямой `python
# scripts/<имя>.py` этого НЕ делает — sys.path[0] становится /app/scripts, и запуск
# падает на ModuleNotFoundError: No module named 'app'.
