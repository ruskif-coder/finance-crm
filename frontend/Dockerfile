FROM node:20-alpine

WORKDIR /app

# Версии зафиксированы lock-файлом (снят с прода 07.10.2026): иначе каждая полная пересборка
# брала бы свежие версии по диапазонам `^`. Обычная выкладка фронта (`deploy.sh frontend`)
# `npm install` не запускает вовсе — только полная пересборка.
COPY package.json package-lock.json ./
RUN npm install --no-audit --no-fund --maxsockets=3

COPY . .

RUN npm run build

CMD ["npm", "start"]