FROM eclipse-temurin:21-jdk-jammy AS build
WORKDIR /workspace
COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
RUN chmod +x mvnw
COPY src/ src/
# verify 包括编译、测试、打包；下载缓存仅供构建使用。
RUN --mount=type=cache,target=/root/.m2 ./mvnw -B -ntp clean verify

FROM eclipse-temurin:21-jre-jammy
WORKDIR /app
# curl 用于健康检查；Ubuntu 基础使用 apt-get，不使用 apk。
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 webgis \
    && useradd --uid 10001 --gid webgis --no-create-home --shell /usr/sbin/nologin webgis
COPY --from=build --chown=webgis:webgis /workspace/target/running-webgis-api-0.0.1-SNAPSHOT.jar /app/app.jar
ENV RUNNING_WEBGIS_DATA_DIR=/data/processed \
    SERVER_ADDRESS=0.0.0.0 \
    SERVER_PORT=8000
USER webgis
EXPOSE 8000
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
