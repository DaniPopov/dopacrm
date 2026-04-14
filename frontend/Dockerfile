FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
# --legacy-peer-deps: openapi-typescript declares TS ^5 but works fine with TS 6
RUN npm ci --legacy-peer-deps

COPY . .

RUN addgroup -S app && adduser -S app -G app \
    && chown -R app:app /app
USER app

EXPOSE 5173

CMD ["npm", "run", "dev"]
