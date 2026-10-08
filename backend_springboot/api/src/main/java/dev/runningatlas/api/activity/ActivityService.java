package dev.runningatlas.api.activity;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import dev.runningatlas.api.common.ApiException;
import dev.runningatlas.api.common.DataReadinessService;
import dev.runningatlas.api.common.JsonValues;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.JsonNodeFactory;
import tools.jackson.databind.node.ObjectNode;

/** Filtering, sorting, paging and lookup operations for activities. */
@Service
public class ActivityService {
    private final ActivityRepository repository;
    private final DataReadinessService readiness;

    public ActivityService(ActivityRepository repository, DataReadinessService readiness) {
        this.repository = repository;
        this.readiness = readiness;
    }

    public ObjectNode list(LocalDate start, LocalDate end, String sport, Boolean hasGps,
            Double minKm, Double maxKm, Sort sort, int offset, int limit) {
        readiness.assertReady();
        if (start != null && end != null && start.isAfter(end)) throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "起始日期不能晚于结束日期。");
        if (minKm != null && maxKm != null && minKm > maxKm) throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "最小距离不能大于最大距离。");
        List<JsonNode> rows = new ArrayList<>();
        repository.activities().forEach(row -> {
            String dateText = JsonValues.text(row, "date");
            LocalDate date = dateText == null ? null : LocalDate.parse(dateText);
            boolean match = (start == null || date != null && !date.isBefore(start))
                    && (end == null || date != null && !date.isAfter(end))
                    && (sport == null || sport.equals(JsonValues.text(row, "sport")))
                    && (hasGps == null || hasGps == row.path("has_gps").asBoolean(false))
                    && (minKm == null || JsonValues.number(row, "distance_m") >= minKm * 1000)
                    && (maxKm == null || JsonValues.number(row, "distance_m") <= maxKm * 1000);
            if (match) rows.add(row);
        });
        Comparator<JsonNode> comparator = switch (sort) {
            case DISTANCE_ASC, DISTANCE_DESC -> Comparator.comparingDouble(row -> JsonValues.number(row, "distance_m"));
            case DATE_ASC, DATE_DESC -> Comparator.comparing(row -> JsonValues.text(row, "start_time"), Comparator.nullsFirst(String::compareTo));
        };
        if (sort == Sort.DATE_DESC || sort == Sort.DISTANCE_DESC) comparator = comparator.reversed();
        rows.sort(comparator);
        int from = Math.min(offset, rows.size());
        int to = Math.min(from + limit, rows.size());
        ArrayNode items = JsonNodeFactory.instance.arrayNode();
        rows.subList(from, to).forEach(items::add);
        ObjectNode result = JsonNodeFactory.instance.objectNode();
        result.put("total", rows.size());
        result.set("items", items);
        return result;
    }

    public ArrayNode calendar() { readiness.assertReady(); return repository.calendar(); }

    public JsonNode detail(String id) {
        readiness.assertReady();
        for (JsonNode row : repository.activities()) if (id.equals(JsonValues.text(row, "id"))) return row;
        throw new ApiException(HttpStatus.NOT_FOUND, "未找到该活动。");
    }

    public ObjectNode track(String id) { readiness.assertReady(); return repository.track(id); }

    public enum Sort {
        DATE_DESC, DATE_ASC, DISTANCE_DESC, DISTANCE_ASC;
        public static Sort parse(String value) {
            try { return valueOf(value.toUpperCase()); }
            catch (IllegalArgumentException exception) {
                throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "sort 参数不合法。");
            }
        }
    }
}
