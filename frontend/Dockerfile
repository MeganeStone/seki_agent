FROM node:24-alpine

WORKDIR /app

COPY frontend/package*.json ./
RUN npm install

COPY frontend ./
RUN VITE_API_BASE_URL=$VITE_API_BASE_URL npm run build

EXPOSE 5173

CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173"]
