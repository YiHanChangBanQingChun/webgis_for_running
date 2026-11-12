package dev.runningatlas.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import dev.runningatlas.api.activity.ActivityInsightsService;
import dev.runningatlas.api.activity.ActivityRepository;
import dev.runningatlas.api.activity.ActivityService;
import dev.runningatlas.api.common.ApiException;
import dev.runningatlas.api.common.DataReadinessService;
import dev.runningatlas.api.config.RunningWebgisProperties;
import dev.runningatlas.api.exploration.HeatGridService;
import dev.runningatlas.api.statistics.StatisticsService;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.HttpStatus;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.List;

/** 使用人工样本记录重构前的完整响应，防止字段、空值、聚合口径或舍入规则意外变化。 */
class ServiceRegressionTests {
    @TempDir Path directory;

    @Test
    void preservesResponsesAcrossReadabilityRefactoring() throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        Files.createDirectories(directory.resolve("tracks"));
        Files.writeString(
                directory.resolve("import-report.json"), "{\"readiness\":{\"api_ready\":true}}");
        Files.writeString(
                directory.resolve("activities.json"),
                """
                [
                  {"id":"history","date":"2026-09-28","start_time":"2026-09-28T08:00:00","sport":"running","distance_m":5000,"elapsed_s":1800,"average_heart_rate":150,"has_gps":true},
                  {"id":"run","date":"2026-10-01","start_time":"2026-10-01T08:00:00","sport":"running","distance_m":10000,"elapsed_s":3600,"average_heart_rate":160,"total_ascent_m":20,"calories":500,"has_gps":true},
                  {"id":"no-hr","date":"2026-10-05","start_time":"2026-10-05T08:00:00","sport":"running","distance_m":3000,"elapsed_s":1200,"average_heart_rate":null,"has_gps":true},
                  {"id":"excluded","date":"2026-10-01","sport":"running","distance_m":7000,"elapsed_s":2000,"training_excluded":true},
                  {"id":"hike","date":"2026-10-02","sport":"hiking","distance_m":15000,"elapsed_s":10000}
                ]
                """);
        ObjectNode track = mapper.createObjectNode();
        ObjectNode series =
                track.putArray("features").addObject().putObject("properties").putObject("series");
        var distances = series.putArray("distance");
        var speeds = series.putArray("speed");
        var heartRates = series.putArray("heart_rate");
        var altitudes = series.putArray("altitude");
        for (int i = 0; i < 80; i++) {
            distances.add(i * 40);
            speeds.add(i % 15 == 0 ? 0.2 : 3 + (i % 3) * 0.1);
            heartRates.add(i < 40 ? 140 : 160);
            altitudes.add(i * 0.5);
        }
        Files.writeString(directory.resolve("tracks/run.geojson"), track.toString());
        Files.writeString(
                directory.resolve("spatial-grid.json"),
                """
                {"cell_size_m":250,"cells":[{"cell_id":"sample","longitude":113.3,"latitude":23.1,
                "activities":[{"date":"2026-10-01","distance_m":123.45},{"date":"2026-10-02","distance_m":100}]}]}
                """);
        var repository =
                new ActivityRepository(
                        new RunningWebgisProperties(directory.toString(), List.of()), mapper);
        var readiness = new DataReadinessService(repository);
        var statistics = new StatisticsService(repository, readiness);
        var activities = new ActivityService(repository, readiness);
        var result = mapper.createObjectNode();
        result.set("monthly", statistics.monthly("2026-10"));
        result.set(
                "range",
                statistics.range(LocalDate.parse("2026-10-01"), LocalDate.parse("2026-10-07")));
        result.set(
                "empty",
                statistics.range(LocalDate.parse("2027-01-01"), LocalDate.parse("2027-01-02")));
        result.set(
                "activities",
                activities.list(
                        null,
                        null,
                        "running",
                        null,
                        null,
                        null,
                        ActivityService.Sort.DISTANCE_DESC,
                        1,
                        2));
        result.set("insights", new ActivityInsightsService(repository, readiness).analyze("run"));
        result.set("grid", new HeatGridService(repository, readiness).query(null, null, 1));
        try (var input = getClass().getResourceAsStream("/service-responses.json")) {
            assertThat(input).isNotNull();
            JsonNode expected = mapper.readTree(input);
            // 比较真正输出的 JSON；消除 LongNode 与 IntNode 等 Java 内部节点类型差异。
            JsonNode actual = mapper.readTree(mapper.writeValueAsString(result));
            assertThat(actual).isEqualTo(expected);
        }
    }

    /** 错误输入应在读取业务文件前被拒绝，并保留原接口的状态码。 */
    @Test
    void preservesValidationAndMissingFileErrors() throws Exception {
        Files.writeString(
                directory.resolve("import-report.json"), "{\"readiness\":{\"api_ready\":true}}");
        var repository =
                new ActivityRepository(
                        new RunningWebgisProperties(directory.toString(), List.of()),
                        new ObjectMapper());
        var readiness = new DataReadinessService(repository);
        var statistics = new StatisticsService(repository, readiness);
        LocalDate start = LocalDate.parse("2026-10-01");

        assertThatThrownBy(() -> statistics.monthly("2026-13"))
                .isInstanceOfSatisfying(
                        ApiException.class,
                        error ->
                                assertThat(error.status())
                                        .isEqualTo(HttpStatus.UNPROCESSABLE_ENTITY));
        assertThatThrownBy(() -> statistics.range(start, start.minusDays(1)))
                .isInstanceOfSatisfying(
                        ApiException.class,
                        error ->
                                assertThat(error.status())
                                        .isEqualTo(HttpStatus.UNPROCESSABLE_ENTITY));
        assertThatThrownBy(() -> statistics.range(start, start.plusDays(1096)))
                .isInstanceOfSatisfying(
                        ApiException.class,
                        error ->
                                assertThat(error.status())
                                        .isEqualTo(HttpStatus.UNPROCESSABLE_ENTITY));
        assertThatThrownBy(() -> new HeatGridService(repository, readiness).query(null, null, 0))
                .isInstanceOfSatisfying(
                        ApiException.class,
                        error ->
                                assertThat(error.status())
                                        .isEqualTo(HttpStatus.UNPROCESSABLE_ENTITY));
        assertThatThrownBy(() -> repository.track("../outside"))
                .isInstanceOfSatisfying(
                        ApiException.class,
                        error -> assertThat(error.status()).isEqualTo(HttpStatus.BAD_REQUEST));
        assertThatThrownBy(() -> repository.track("missing"))
                .isInstanceOfSatisfying(
                        ApiException.class,
                        error -> assertThat(error.status()).isEqualTo(HttpStatus.NOT_FOUND));
    }
}
