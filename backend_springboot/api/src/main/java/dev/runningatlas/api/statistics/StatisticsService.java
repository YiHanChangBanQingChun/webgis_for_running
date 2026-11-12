package dev.runningatlas.api.statistics;

import dev.runningatlas.api.activity.ActivityRepository;
import dev.runningatlas.api.common.ApiException;
import dev.runningatlas.api.common.DataReadinessService;
import dev.runningatlas.api.common.JsonValues;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.JsonNodeFactory;
import tools.jackson.databind.node.ObjectNode;

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

/**
 * 训练统计业务层：聚合月度摘要、逐日数据、逐周数据和滚动训练负荷。
 *
 * <p>与 FastAPI 迁移接口保持同一业务约定；月度统计与区间分析的运动类型筛选口径并不相同。 相对负荷是本项目基于时长与心率计算的观察指标，不是 COROS 官方负荷。
 */
@Service
public class StatisticsService {
    private final ActivityRepository repository;
    private final DataReadinessService readiness;

    /**
     * 通过构造器接收依赖；Spring 创建组件时自动提供这些实例，无需手工 new。
     *
     * @param repository 只读派生文件访问层，由 Spring 注入
     * @param readiness 统一数据就绪检查服务，由 Spring 注入
     */
    public StatisticsService(ActivityRepository repository, DataReadinessService readiness) {
        this.repository = repository;
        this.readiness = readiness;
    }

    /**
     * 统计指定月份未被排除的全部运动；保留各运动类型计数。
     *
     * @param text 待解析的月份字符串（YYYY-MM）
     * @return 月份、活动次数、距离、时长、配速及运动类型计数
     * @throws ApiException 月份格式错误时为 422；数据未就绪时为 503
     */
    public ObjectNode monthly(String text) {
        readiness.assertReady();
        final YearMonth month;
        try {
            month = YearMonth.parse(text);
        } catch (DateTimeParseException e) {
            throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "month 必须使用 YYYY-MM 格式。");
        }
        List<JsonNode> rows = new ArrayList<>();
        for (JsonNode row : repository.activities()) {
            String d = JsonValues.text(row, "date");
            if (d != null
                    && d.startsWith(month.toString())
                    && !row.path("training_excluded").asBoolean(false)) {
                rows.add(row);
            }
        }
        double distance = sum(rows, "distance_m");
        double elapsed = sum(rows, "elapsed_s");
        Set<String> days = new LinkedHashSet<>();
        Map<String, Integer> sports = new TreeMap<>();
        for (JsonNode row : rows) {
            days.add(JsonValues.text(row, "date"));
            String sport = JsonValues.text(row, "sport");
            sports.merge(sport == null ? "unknown" : sport, 1, Integer::sum);
        }
        ObjectNode result = JsonNodeFactory.instance.objectNode();
        result.put("month", month.toString());
        result.put("activity_count", rows.size());
        result.put("active_days", days.size());
        result.put("total_distance_m", round(distance));
        result.put("total_elapsed_s", round(elapsed));
        put(result, "average_distance_m", days.isEmpty() ? null : distance / days.size());
        put(result, "average_pace_s_per_km", distance == 0 ? null : elapsed / distance * 1000);
        result.put("total_ascent_m", round(sum(rows, "total_ascent_m")));
        result.put(
                "activities_with_gps",
                rows.stream().filter(r -> r.path("has_gps").asBoolean(false)).count());
        ObjectNode counts = result.putObject("sport_counts");
        sports.forEach(counts::put);
        return result;
    }

    /**
     * 分析闭区间 [start, end] 内的正式跑步，并提前读取 27 天用于滚动负荷计算。
     *
     * @param start 开始日期，包含当天，必填
     * @param end 结束日期，包含当天，必填
     * @return 含 summary、daily、weekly 和负荷说明的统计结果
     * @throws ApiException 日期颠倒或范围超过 1095 天时为 422；数据未就绪时为 503
     */
    public ObjectNode range(LocalDate start, LocalDate end) {
        readiness.assertReady();
        if (start.isAfter(end)) {
            throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "起始日期不能晚于结束日期。");
        }
        if (ChronoUnit.DAYS.between(start, end) > 1095) {
            throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "单次统计范围不能超过三年。");
        }
        // 用户只看所选区间，但首日的 28 日负荷还需要前 27 天的历史。
        LocalDate historyStart = start.minusDays(27);
        Map<LocalDate, List<JsonNode>> byDay = new LinkedHashMap<>();
        List<JsonNode> history = new ArrayList<>();
        for (JsonNode row : repository.activities()) {
            if (!"running".equals(JsonValues.text(row, "sport"))
                    || row.path("training_excluded").asBoolean(false)) {
                continue;
            }
            String text = JsonValues.text(row, "date");
            if (text == null) {
                continue;
            }
            LocalDate date = LocalDate.parse(text);
            if (!date.isBefore(historyStart) && !date.isAfter(end)) {
                history.add(row);
                byDay.computeIfAbsent(date, ignored -> new ArrayList<>()).add(row);
            }
        }
        List<Daily> daily = buildDailyEntries(historyStart, end, byDay);
        calculateRollingLoads(daily);

        // 隐藏用于计算基线的历史，只把用户选中的日期返回给前端。
        List<Daily> visible = daily.stream().filter(day -> !day.date.isBefore(start)).toList();
        return buildRangeResponse(start, end, history, visible);
    }

    /**
     * 为每个自然日建立记录，包括没有运动的日期，保证滑动窗口按天而非按活动次数计算。
     *
     * @param historyStart 包含额外历史的开始日期
     * @param end 区间结束日期，包含当天
     * @param byDay 按日期分组的正式跑步摘要
     * @return 连续且按日期递增的逐日统计
     */
    private List<Daily> buildDailyEntries(
            LocalDate historyStart, LocalDate end, Map<LocalDate, List<JsonNode>> byDay) {
        List<Daily> daily = new ArrayList<>();
        for (LocalDate date = historyStart; !date.isAfter(end); date = date.plusDays(1)) {
            List<JsonNode> items = byDay.getOrDefault(date, List.of());
            double elapsed = sum(items, "elapsed_s");
            double weighted = 0;
            double hrSeconds = 0;
            for (JsonNode item : items) {
                double hr = JsonValues.number(item, "average_heart_rate");
                double seconds = JsonValues.number(item, "elapsed_s");
                if (hr > 0) {
                    weighted += hr * seconds;
                    hrSeconds += seconds;
                }
            }
            // 心率按有效记录的运动时长加权；没有心率时不能伪造一个 0 bpm。
            Double avgHr = hrSeconds == 0 ? null : weighted / hrSeconds;
            // 相对负荷 = 分钟数 × (平均心率 / 150)²；无心率时使用原有回退系数。
            double load = elapsed / 60 * (avgHr == null ? .65 : Math.pow(avgHr / 150, 2));
            daily.add(
                    new Daily(
                            date,
                            items.size(),
                            sum(items, "distance_m"),
                            elapsed,
                            sum(items, "total_ascent_m"),
                            sum(items, "calories"),
                            avgHr,
                            load));
        }
        return daily;
    }

    /**
     * 在日记录上补充滚动负荷；最后一天包含在窗口内，累计时保留原始计算精度。
     *
     * @param daily 连续的逐日统计，会原地补充 load7、load28 和 ratio
     */
    private void calculateRollingLoads(List<Daily> daily) {
        for (int i = 0; i < daily.size(); i++) {
            Daily item = daily.get(i);
            item.load7 = loadSum(daily, Math.max(0, i - 6), i);
            item.load28 = loadSum(daily, Math.max(0, i - 27), i);
            // 将累计 28 日负荷换算为每周基线，再与最近 7 日负荷比较。
            double weeks = Math.min(4, (i + 1) / 7.0);
            double base = item.load28 == 0 ? 0 : item.load28 / weeks;
            item.ratio = base == 0 ? null : item.load7 / base;
        }
    }

    /**
     * 组装前端区间分析所需的 summary、daily、weekly，保留既有字段名和舍入口径。
     *
     * @param start 用户选择的开始日期
     * @param end 用户选择的结束日期
     * @param history 含额外 27 天历史的正式跑步记录
     * @param visible 仅包含用户所选日期的逐日统计
     * @return 完整区间分析响应
     */
    private ObjectNode buildRangeResponse(
            LocalDate start, LocalDate end, List<JsonNode> history, List<Daily> visible) {
        Map<LocalDate, Weekly> weekly = new LinkedHashMap<>();
        // 以周一的日期作为周标识。区间首尾可以只包含某周的一部分。
        for (Daily day : visible) {
            LocalDate monday = day.date.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
            Weekly week = weekly.computeIfAbsent(monday, Weekly::new);
            week.add(day);
        }
        List<JsonNode> selected =
                history.stream()
                        .filter(r -> !LocalDate.parse(JsonValues.text(r, "date")).isBefore(start))
                        .toList();
        double distance = sum(selected, "distance_m");
        double elapsed = sum(selected, "elapsed_s");
        Set<String> days = new LinkedHashSet<>();
        selected.forEach(r -> days.add(JsonValues.text(r, "date")));
        Double ratio = visible.isEmpty() ? null : visible.getLast().ratio;
        ObjectNode result = JsonNodeFactory.instance.objectNode();
        result.put("start", start.toString());
        result.put("end", end.toString());
        ObjectNode summary = result.putObject("summary");
        summary.put("activity_count", selected.size());
        summary.put("active_days", days.size());
        summary.put("total_distance_m", round(distance));
        summary.put("total_elapsed_s", round(elapsed));
        summary.put("total_ascent_m", round(sum(selected, "total_ascent_m")));
        summary.put("calories", round(sum(selected, "calories")));
        put(summary, "average_pace_s_per_km", distance == 0 ? null : elapsed / distance * 1000);
        put(summary, "average_distance_m", days.isEmpty() ? null : distance / days.size());
        put(summary, "load_ratio", ratio);
        summary.put("load_status", status(ratio));
        ArrayNode dayArray = result.putArray("daily");
        visible.forEach(d -> dayArray.add(d.json()));
        ArrayNode weekArray = result.putArray("weekly");
        weekly.values().forEach(w -> weekArray.add(w.json()));
        result.put("load_note", "仅统计正式跑步；相对负荷基于时长与平均心率，不是 COROS 负荷。混合／排除活动与其他运动保留在活动列表。");
        return result;
    }

    /**
     * 累加指定数值字段，缺失或非数值字段按 0 处理。
     *
     * @param rows 参与统计的活动或逐日记录集合
     * @param field 待读取或写入的 JSON 字段名
     * @return 所选字段或区间的累计值
     */
    private double sum(List<JsonNode> rows, String field) {
        return rows.stream().mapToDouble(r -> JsonValues.number(r, field)).sum();
    }

    /**
     * 累加闭区间索引 [from, to] 中的原始日负荷，不提前舍入。
     *
     * @param rows 参与统计的活动或逐日记录集合
     * @param from 起始索引，包含该位置
     * @param to 结束索引，包含该位置
     * @return 所选字段或区间的累计值
     */
    private double loadSum(List<Daily> rows, int from, int to) {
        double totalLoad = 0;
        for (int i = from; i <= to; i++) {
            totalLoad += rows.get(i).load;
        }
        return totalLoad;
    }

    /**
     * 按指定位数四舍五入；统计服务默认保留两位小数。
     *
     * @param value 待转换、舍入或校验的值
     * @return 按约定位数舍入后的数值
     */
    private double round(double value) {
        return JsonValues.round(value, 2);
    }

    /**
     * 输出可空数值；null 或非有限值写为 JSON null，否则按当前服务口径舍入。
     *
     * @param node 目标 JSON 响应对象
     * @param field 输出 JSON 字段名
     * @param value 可空的数值或负荷比
     */
    private void put(ObjectNode node, String field, Double value) {
        if (value == null || !Double.isFinite(value)) {
            node.putNull(field);
        } else {
            node.put(field, round(value));
        }
    }

    /**
     * 按负荷比划分状态：低于 0.75 为恢复，至 1.25 为稳定，至 1.5 为上升，更高为高负荷。
     *
     * @param v 可空的数值或负荷比
     * @return 供前端展示的负荷状态编码
     */
    private String status(Double v) {
        if (v == null) {
            return "insufficient";
        }
        if (v < .75) {
            return "recovery";
        }
        if (v <= 1.25) {
            return "balanced";
        }
        if (v <= 1.5) {
            return "rising";
        }
        return "high";
    }

    /** 逐日统计的内部状态；先汇总当天数据，再补充 7 日、28 日负荷与比值。 */
    private final class Daily {
        final LocalDate date;
        final int count;
        final double distance;
        final double elapsed;
        final double ascent;
        final double calories;
        final Double avgHr;
        final double load;
        double load7;
        double load28;
        Double ratio;

        /**
         * 保存当天的汇总值；滚动负荷由外层服务在所有日期构建完成后补充。
         *
         * @param date 统计日期
         * @param count 当天活动次数
         * @param distance 累计距离，单位米
         * @param elapsed 累计时长，单位秒
         * @param ascent 累计爬升，单位米
         * @param calories 累计热量，单位千卡
         * @param hr 按时长加权的平均心率，无有效心率时为 null
         * @param load 当天原始相对负荷
         */
        Daily(
                LocalDate date,
                int count,
                double distance,
                double elapsed,
                double ascent,
                double calories,
                Double hr,
                double load) {
            this.date = date;
            this.count = count;
            this.distance = distance;
            this.elapsed = elapsed;
            this.ascent = ascent;
            this.calories = calories;
            avgHr = hr;
            this.load = load;
        }

        /**
         * 把内部统计对象转换为前端约定的 JSON 字段，并在输出时舍入。
         *
         * @return 包含日期、距离、心率与滚动负荷的逐日响应对象
         */
        ObjectNode json() {
            ObjectNode n = JsonNodeFactory.instance.objectNode();
            n.put("date", date.toString());
            n.put("activity_count", count);
            n.put("distance_m", round(distance));
            n.put("elapsed_s", round(elapsed));
            n.put("total_ascent_m", round(ascent));
            n.put("calories", round(calories));
            if (avgHr == null) {
                n.putNull("average_heart_rate");
            } else {
                n.put("average_heart_rate", JsonValues.round(avgHr, 1));
            }
            n.put("relative_load", round(load));
            n.put("load_7d", round(load7));
            n.put("load_28d", round(load28));
            put(n, "load_ratio", ratio);
            return n;
        }
    }

    /** 按周一日期分组的周统计累加器；仅汇总用户所选范围内的可见日期。 */
    private final class Weekly {
        final LocalDate week;
        int count;
        double distance;
        double elapsed;
        double load;

        /**
         * 创建一周的累加器；数值字段初始为 0，随后由 add 方法逐日累加。
         *
         * @param week 所属周的周一日期
         */
        Weekly(LocalDate week) {
            this.week = week;
        }

        /**
         * 把一天的数据累加到所属周，保留原始精度直到输出。
         *
         * @param day 待累加的当天统计
         */
        void add(Daily day) {
            count += day.count;
            distance += day.distance;
            elapsed += day.elapsed;
            load += day.load;
        }

        /**
         * 把内部统计对象转换为前端约定的 JSON 字段，并在输出时舍入。
         *
         * @return 包含周标识、活动次数、距离、时长和负荷的逐周响应对象
         */
        ObjectNode json() {
            ObjectNode n = JsonNodeFactory.instance.objectNode();
            n.put("week", week.toString());
            n.put("activity_count", count);
            n.put("distance_m", round(distance));
            n.put("elapsed_s", round(elapsed));
            n.put("relative_load", round(load));
            return n;
        }
    }
}
