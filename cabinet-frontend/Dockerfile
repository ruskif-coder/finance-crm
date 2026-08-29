FROM node:20-alpine

WORKDIR /app

COPY package.json .
RUN npm install --no-audit --no-fund --maxsockets=3

COPY . .

RUN npm run build

CMD ["npm", "start"]
