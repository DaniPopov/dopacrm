FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

RUN addgroup -S app && adduser -S app -G app
USER app

EXPOSE 5173

CMD ["npm", "run", "dev"]
