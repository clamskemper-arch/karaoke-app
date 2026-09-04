# --- Build ---------------------------------------------------------------
FROM eclipse-temurin:21-jdk AS build
WORKDIR /app

# Erst nur die Wrapper-/POM-Dateien -> Dependency-Layer wird gecached, solange
# sich pom.xml nicht aendert
COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
RUN chmod +x mvnw && ./mvnw -q -B dependency:go-offline

COPY src/ src/
RUN ./mvnw -q -B clean package -DskipTests \
    && cp target/*.jar app.jar

# --- Runtime ------------------------------------------------------------
FROM eclipse-temurin:21-jre AS runtime
WORKDIR /app

# curl fuer den HEALTHCHECK; nicht als root laufen. /data ist das persistente
# Volume (H2-DB + hochgeladene Song-Dateien).
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -r -u 1001 spring \
    && mkdir -p /data && chown -R spring:spring /data /app
USER spring

ENV KARAOKE_DB_FILE=/data/karaoke-db \
    KARAOKE_STORAGE_DIR=/data/songs \
    PORT=8080

COPY --from=build /app/app.jar app.jar
VOLUME /data
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=45s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/actuator/health" | grep -q '"status":"UP"' || exit 1

ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-jar", "app.jar"]
