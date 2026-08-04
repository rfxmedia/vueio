FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS build

WORKDIR /app
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html vite.config.js ./
COPY src ./src
COPY nginx.conf nginx-api-proxy.conf ./
RUN chmod 0444 nginx.conf nginx-api-proxy.conf && npm run build

FROM nginxinc/nginx-unprivileged:1.31.3-alpine3.24@sha256:59ccf0943b0b8e8d9e6ea9039a39555730f544701a655c596f7df7d096c593f5
LABEL org.opencontainers.image.title="Vue.io UI" \
      org.opencontainers.image.licenses="PolyForm-Perimeter-1.0.1" \
      org.opencontainers.image.url="https://polyformproject.org/licenses/perimeter/1.0.1"
ENV VUEIO_TRUST_UPSTREAM_PROXY=false
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=build /app/nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/nginx-api-proxy.conf /etc/nginx/vueio-api-proxy.inc
USER 101
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
