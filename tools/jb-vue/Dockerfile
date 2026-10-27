ARG NODE_IMAGE
ARG BASE_IMAGE
FROM ${NODE_IMAGE} AS dependencies
WORKDIR /tool
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund

FROM ${BASE_IMAGE}
COPY --from=dependencies /tool/node_modules /opt/webuddy-vue/node_modules
