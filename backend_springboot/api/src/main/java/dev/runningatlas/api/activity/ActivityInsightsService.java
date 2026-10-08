package dev.runningatlas.api.activity;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import dev.runningatlas.api.common.ApiException;
import dev.runningatlas.api.common.DataReadinessService;
import dev.runningatlas.api.common.JsonValues;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.JsonNodeFactory;
import tools.jackson.databind.node.ObjectNode;

/** Computes pace variability, heart-rate drift, stop ratio, training type and kilometre splits. */
@Service
public class ActivityInsightsService {
    private final ActivityRepository repository;
    private final DataReadinessService readiness;

    public ActivityInsightsService(ActivityRepository repository, DataReadinessService readiness) {
        this.repository = repository;
        this.readiness = readiness;
    }

    public ObjectNode analyze(String id) {
        readiness.assertReady();
        JsonNode features = repository.track(id).path("features");
        if (!features.isArray() || features.isEmpty()) throw new ApiException(HttpStatus.NOT_FOUND, "该活动没有可分析的 GPS 轨迹。");
        JsonNode series = features.get(0).path("properties").path("series");
        ArrayNode distance = array(series.path("distance"));
        ArrayNode speed = preferred(series, "enhanced_speed", "speed");
        ArrayNode heartRate = array(series.path("heart_rate"));
        ArrayNode altitude = preferred(series, "enhanced_altitude", "altitude");

        List<Double> paces = new ArrayList<>();
        int numeric = 0, stopped = 0;
        for (JsonNode value : speed) if (value.isNumber()) {
            double v = value.asDouble(); numeric++;
            if (v < .5) stopped++;
            if (v >= .8 && v <= 8) paces.add(1000 / v);
        }
        Double paceCv = paces.size() > 2 ? deviation(paces) / average(paces) * 100 : null;
        Double stopRatio = numeric == 0 ? null : (double) stopped / numeric;
        double totalDistance = 0;
        for (JsonNode value : distance) if (value.isNumber()) totalDistance = Math.max(totalDistance, value.asDouble());

        List<Double> first = new ArrayList<>(), second = new ArrayList<>();
        for (int i = 0; i < distance.size(); i++) {
            Double d = numberAt(distance, i), s = numberAt(speed, i), hr = numberAt(heartRate, i);
            if (d == null || s == null || hr == null || s < .8 || hr <= 0) continue;
            (d <= totalDistance / 2 ? first : second).add(s / hr);
        }
        Double drift = null;
        if (first.size() >= 30 && second.size() >= 30) {
            double a = average(first); drift = a == 0 ? null : (a - average(second)) / a * 100;
        }
        String type = paceCv == null ? "数据不足"
                : paceCv < 6 && value(stopRatio) < .04 ? "稳定跑"
                : paceCv >= 14 || value(stopRatio) >= .08 ? "变速 / 间歇特征" : "节奏变化跑";

        Map<Integer, Bucket> buckets = new TreeMap<>();
        int lastKm = (int) Math.ceil(totalDistance / 1000);
        for (int i = 0; i < distance.size(); i++) {
            Double d = numberAt(distance, i); if (d == null) continue;
            int km = (int) Math.floor(d / 1000) + 1; if (km > lastKm) continue;
            Bucket bucket = buckets.computeIfAbsent(km, ignored -> new Bucket());
            Double s = numberAt(speed, i), hr = numberAt(heartRate, i), alt = numberAt(altitude, i);
            if (s != null && s > .8) bucket.speeds.add(s);
            if (hr != null) bucket.heartRates.add(hr);
            if (alt != null) bucket.altitudes.add(alt);
        }
        ArrayNode splits = JsonNodeFactory.instance.arrayNode();
        buckets.forEach((km, b) -> {
            ObjectNode split = splits.addObject(); split.put("kilometer", km);
            put(split, "pace_s_per_km", b.speeds.isEmpty() ? null : 1000 / average(b.speeds));
            put(split, "average_heart_rate", avgOrNull(b.heartRates));
            put(split, "average_altitude_m", avgOrNull(b.altitudes));
        });
        ObjectNode result = JsonNodeFactory.instance.objectNode();
        result.put("activity_id", id); put(result, "pace_cv_percent", paceCv); put(result, "heart_rate_drift_percent", drift);
        put(result, "stopped_ratio_percent", stopRatio == null ? null : stopRatio * 100);
        result.put("training_type", type); result.set("splits", splits);
        ObjectNode notes = result.putObject("notes");
        notes.put("heart_rate_drift", "比较前后半程速度/心率效率变化，仅作为训练观察。");
        notes.put("classification", "由配速波动与低速占比自动推测，可与实际训练内容不同。");
        return result;
    }

    private ArrayNode preferred(JsonNode parent, String first, String second) { ArrayNode a = array(parent.path(first)); return a.isEmpty() ? array(parent.path(second)) : a; }
    private ArrayNode array(JsonNode node) { return node instanceof ArrayNode a ? a : JsonNodeFactory.instance.arrayNode(); }
    private Double numberAt(ArrayNode a, int i) { return i < a.size() ? JsonValues.nullableNumber(a.get(i)) : null; }
    private double average(List<Double> values) { return values.stream().mapToDouble(Double::doubleValue).average().orElse(0); }
    private Double avgOrNull(List<Double> values) { return values.isEmpty() ? null : average(values); }
    private double deviation(List<Double> values) { double mean = average(values); return Math.sqrt(values.stream().mapToDouble(v -> Math.pow(v - mean, 2)).average().orElse(0)); }
    private double value(Double v) { return v == null ? 0 : v; }
    private void put(ObjectNode node, String field, Double value) { if (value == null || !Double.isFinite(value)) node.putNull(field); else node.put(field, JsonValues.round(value, 1)); }

    private static final class Bucket {
        private final List<Double> speeds = new ArrayList<>(), heartRates = new ArrayList<>(), altitudes = new ArrayList<>();
    }
}
