FROM maven:3.9-eclipse-temurin-8 AS java8
FROM node:24-bookworm-slim@sha256:01d566e8d94d8c619591d78652babfccd3c6992a3dffa9ed5ab39e11cf6c70e9 AS node
FROM jenkins/jenkins:lts-jdk21@sha256:74401de6a6f92e1afe1b02d1c8e3d0c33f263bfb5275dd8813f9150355f2367b
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 chromium mariadb-client fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
COPY --from=java8 /opt/java/openjdk /opt/java8
COPY --from=java8 /usr/share/maven /opt/maven
COPY --from=node /usr/local /usr/local
USER jenkins
RUN jenkins-plugin-cli --plugins git junit workflow-aggregator matrix-auth
