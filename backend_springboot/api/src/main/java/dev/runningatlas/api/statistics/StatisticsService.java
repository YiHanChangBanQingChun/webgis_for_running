package dev.runningatlas.api.statistics;

import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.format.DateTimeParseException;
import java.time.temporal.ChronoUnit;
import java.time.temporal.TemporalAdjusters;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import dev.runningatlas.api.activity.ActivityRepository;
import dev.runningatlas.api.common.ApiException;
import dev.runningatlas.api.common.DataReadinessService;
import dev.runningatlas.api.common.JsonValues;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.JsonNodeFactory;
import tools.jackson.databind.node.ObjectNode;

/** Aggregates activity summaries and calculates the same rolling load model as FastAPI. */
@Service
public class StatisticsService {
    private final ActivityRepository repository;
    private final DataReadinessService readiness;
    public StatisticsService(ActivityRepository repository, DataReadinessService readiness) { this.repository = repository; this.readiness = readiness; }

    public ObjectNode monthly(String text) {
        readiness.assertReady();
        final YearMonth month;
        try { month = YearMonth.parse(text); } catch (DateTimeParseException e) { throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "month 必须使用 YYYY-MM 格式。"); }
        List<JsonNode> rows = new ArrayList<>();
        for (JsonNode row : repository.activities()) { String d = JsonValues.text(row, "date"); if (d != null && d.startsWith(month.toString()) && !row.path("training_excluded").asBoolean(false)) rows.add(row); }
        double distance = sum(rows, "distance_m"), elapsed = sum(rows, "elapsed_s");
        Set<String> days = new LinkedHashSet<>(); Map<String, Integer> sports = new TreeMap<>();
        for (JsonNode row : rows) { days.add(JsonValues.text(row, "date")); String sport = JsonValues.text(row, "sport"); sports.merge(sport == null ? "unknown" : sport, 1, Integer::sum); }
        ObjectNode result = JsonNodeFactory.instance.objectNode(); result.put("month", month.toString()); result.put("activity_count", rows.size()); result.put("active_days", days.size());
        result.put("total_distance_m", round(distance)); result.put("total_elapsed_s", round(elapsed));
        put(result, "average_distance_m", days.isEmpty() ? null : distance / days.size()); put(result, "average_pace_s_per_km", distance == 0 ? null : elapsed / distance * 1000);
        result.put("total_ascent_m", round(sum(rows, "total_ascent_m"))); result.put("activities_with_gps", rows.stream().filter(r -> r.path("has_gps").asBoolean(false)).count());
        ObjectNode counts = result.putObject("sport_counts"); sports.forEach(counts::put); return result;
    }

    public ObjectNode range(LocalDate start, LocalDate end) {
        readiness.assertReady();
        if (start.isAfter(end)) throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "起始日期不能晚于结束日期。");
        if (ChronoUnit.DAYS.between(start, end) > 1095) throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "单次统计范围不能超过三年。");
        LocalDate historyStart = start.minusDays(27); Map<LocalDate, List<JsonNode>> byDay = new LinkedHashMap<>(); List<JsonNode> history = new ArrayList<>();
        for (JsonNode row : repository.activities()) {
            if (!"running".equals(JsonValues.text(row, "sport")) || row.path("training_excluded").asBoolean(false)) continue;
            String text = JsonValues.text(row, "date"); if (text == null) continue; LocalDate date = LocalDate.parse(text);
            if (!date.isBefore(historyStart) && !date.isAfter(end)) { history.add(row); byDay.computeIfAbsent(date, ignored -> new ArrayList<>()).add(row); }
        }
        List<Daily> daily = new ArrayList<>();
        for (LocalDate date = historyStart; !date.isAfter(end); date = date.plusDays(1)) {
            List<JsonNode> items = byDay.getOrDefault(date, List.of()); double elapsed = sum(items, "elapsed_s"), weighted = 0, hrSeconds = 0;
            for (JsonNode item : items) { double hr = JsonValues.number(item, "average_heart_rate"), seconds = JsonValues.number(item, "elapsed_s"); if (hr > 0) { weighted += hr * seconds; hrSeconds += seconds; } }
            Double avgHr = hrSeconds == 0 ? null : weighted / hrSeconds; double load = elapsed / 60 * (avgHr == null ? .65 : Math.pow(avgHr / 150, 2));
            daily.add(new Daily(date, items.size(), sum(items, "distance_m"), elapsed, sum(items, "total_ascent_m"), sum(items, "calories"), avgHr, load));
        }
        for (int i = 0; i < daily.size(); i++) { Daily item = daily.get(i); item.load7 = loadSum(daily, Math.max(0, i - 6), i); item.load28 = loadSum(daily, Math.max(0, i - 27), i); double weeks = Math.min(4, (i + 1) / 7.0); double base = item.load28 == 0 ? 0 : item.load28 / weeks; item.ratio = base == 0 ? null : item.load7 / base; }
        List<Daily> visible = daily.stream().filter(d -> !d.date.isBefore(start)).toList(); Map<LocalDate, Weekly> weekly = new LinkedHashMap<>();
        visible.forEach(d -> weekly.computeIfAbsent(d.date.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY)), Weekly::new).add(d));
        List<JsonNode> selected = history.stream().filter(r -> !LocalDate.parse(JsonValues.text(r, "date")).isBefore(start)).toList();
        double distance = sum(selected, "distance_m"), elapsed = sum(selected, "elapsed_s"); Set<String> days = new LinkedHashSet<>(); selected.forEach(r -> days.add(JsonValues.text(r, "date")));
        Double ratio = visible.isEmpty() ? null : visible.getLast().ratio;
        ObjectNode result = JsonNodeFactory.instance.objectNode(); result.put("start", start.toString()); result.put("end", end.toString()); ObjectNode summary = result.putObject("summary");
        summary.put("activity_count", selected.size()); summary.put("active_days", days.size()); summary.put("total_distance_m", round(distance)); summary.put("total_elapsed_s", round(elapsed));
        summary.put("total_ascent_m", round(sum(selected, "total_ascent_m"))); summary.put("calories", round(sum(selected, "calories")));
        put(summary, "average_pace_s_per_km", distance == 0 ? null : elapsed / distance * 1000); put(summary, "average_distance_m", days.isEmpty() ? null : distance / days.size()); put(summary, "load_ratio", ratio); summary.put("load_status", status(ratio));
        ArrayNode dayArray = result.putArray("daily"); visible.forEach(d -> dayArray.add(d.json())); ArrayNode weekArray = result.putArray("weekly"); weekly.values().forEach(w -> weekArray.add(w.json()));
        result.put("load_note", "仅统计正式跑步；相对负荷基于时长与平均心率，不是 COROS 负荷。混合／排除活动与其他运动保留在活动列表。"); return result;
    }

    private double sum(List<JsonNode> rows, String field) { return rows.stream().mapToDouble(r -> JsonValues.number(r, field)).sum(); }
    private double loadSum(List<Daily> rows, int from, int to) { double v = 0; for (int i = from; i <= to; i++) v += rows.get(i).load; return v; }
    private double round(double value) { return JsonValues.round(value, 2); }
    private void put(ObjectNode n, String f, Double v) { if (v == null || !Double.isFinite(v)) n.putNull(f); else n.put(f, round(v)); }
    private String status(Double v) { if (v == null) return "insufficient"; if (v < .75) return "recovery"; if (v <= 1.25) return "balanced"; if (v <= 1.5) return "rising"; return "high"; }

    private final class Daily {
        final LocalDate date; final int count; final double distance, elapsed, ascent, calories; final Double avgHr; final double load; double load7, load28; Double ratio;
        Daily(LocalDate d, int c, double distance, double elapsed, double ascent, double calories, Double hr, double load) { date=d; count=c; this.distance=distance; this.elapsed=elapsed; this.ascent=ascent; this.calories=calories; avgHr=hr; this.load=load; }
        ObjectNode json() { ObjectNode n=JsonNodeFactory.instance.objectNode(); n.put("date",date.toString()); n.put("activity_count",count); n.put("distance_m",round(distance)); n.put("elapsed_s",round(elapsed)); n.put("total_ascent_m",round(ascent)); n.put("calories",round(calories)); if(avgHr==null)n.putNull("average_heart_rate");else n.put("average_heart_rate",JsonValues.round(avgHr,1)); n.put("relative_load",round(load)); n.put("load_7d",round(load7)); n.put("load_28d",round(load28)); put(n,"load_ratio",ratio); return n; }
    }
    private final class Weekly {
        final LocalDate week; int count; double distance, elapsed, load; Weekly(LocalDate week){this.week=week;} void add(Daily d){count+=d.count;distance+=d.distance;elapsed+=d.elapsed;load+=d.load;}
        ObjectNode json(){ObjectNode n=JsonNodeFactory.instance.objectNode();n.put("week",week.toString());n.put("activity_count",count);n.put("distance_m",round(distance));n.put("elapsed_s",round(elapsed));n.put("relative_load",round(load));return n;}
    }
}
