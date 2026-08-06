# Официальный образ Playwright — Chromium и системные зависимости уже внутри
# (версия тега должна совпадать с playwright в package.json).
FROM mcr.microsoft.com/playwright:v1.48.0-jammy

WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY server.js ./

ENV NODE_ENV=production
EXPOSE 3001
CMD ["node", "server.js"]
