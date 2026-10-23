package dev.runningatlas.api.activity;

import dev.runningatlas.api.common.ApiException;
import dev.runningatlas.api.common.DataReadinessService;
import dev.runningatlas.api.common.JsonValues;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.JsonNodeFactory;
import tools.jackson.databind.node.ObjectNode;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * 单次活动洞察服务：从轨迹采样序列计算配速波动、心率漂移、停顿比例及分公里指标。
 *
 * <p>数组使用同一索引对应同一采样点；缺失值不能直接当成真实测量值。 所有计算沿用迁移版本的口径，训练类型仅为规则推测，不是设备官方结论。
 */
@Service
public class ActivityInsightsService {
    private final ActivityRepository repository;
    private final DataReadinessService readiness;

    /**
     * 通过构造器接收依赖；Spring 创建组件时自动提供这些实例，无需手工 new。
     *
     * @param repository 只读派生文件访问层，由 Spring 注入
     * @param readiness 统一数据就绪检查服务，由 Spring 注入
     */
    public ActivityInsightsService(ActivityRepository repository, DataReadinessService readiness) {
        this.repository = repository;
        this.readiness = readiness;
    }

    /**
     * 计算采样指标并组装洞察响应；样本不足的指标返回 JSON null。
     *
     * @param id 活动 ID
     * @return 含配速波动、心率漂移、停顿比例、训练类型及分公里统计的对象
     * @throws ApiException 轨迹文件或要素不存在时为 404；数据未就绪时为 503
     */
    public ObjectNode analyze(String id) {
        readiness.assertReady();
        JsonNode features = repository.track(id).path("features");
        if (!features.isArray() || features.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "该活动没有可分析的 GPS 轨迹。");
        }
        JsonNode series = features.get(0).path("properties").path("series");
        ArrayNode distance = array(series.path("distance"));
        ArrayNode speed = preferred(series, "enhanced_speed", "speed");
        ArrayNode heartRate = array(series.path("heart_rate"));
        ArrayNode altitude = preferred(series, "enhanced_altitude", "altitude");

        // 只把 0.8～8 m/s 的采样转换为配速，避免静止或异常速度放大波动指标。
        List<Double> paces = new ArrayList<>();
        int numeric = 0;
        int stopped = 0;
        for (JsonNode value : speed) {
            if (value.isNumber()) {
                double v = value.asDouble();
                numeric++;
                if (v < .5) {
                    stopped++;
                }
                if (v >= .8 && v <= 8) {
                    paces.add(1000 / v);
                }
            }
        }
        Double paceCv = paces.size() > 2 ? deviation(paces) / average(paces) * 100 : null;
        Double stopRatio = numeric == 0 ? null : (double) stopped / numeric;
        double totalDistance = maximumDistance(distance);
        Double drift = calculateHeartRateDrift(distance, speed, heartRate, totalDistance);
        String type = classifyTrainingType(paceCv, stopRatio);
        ArrayNode splits =
                buildKilometerSplits(distance, speed, heartRate, altitude, totalDistance);

        ObjectNode result = JsonNodeFactory.instance.objectNode();
        result.put("activity_id", id);
        put(result, "pace_cv_percent", paceCv);
        put(result, "heart_rate_drift_percent", drift);
        put(result, "stopped_ratio_percent", stopRatio == null ? null : stopRatio * 100);
        result.put("training_type", type);
        result.set("splits", splits);
        ObjectNode notes = result.putObject("notes");
        notes.put("heart_rate_drift", "比较前后半程速度/心率效率变化，仅作为训练观察。");
        notes.put("classification", "由配速波动与低速占比自动推测，可与实际训练内容不同。");
        return result;
    }

    /**
     * 用累计距离的最大有效值确定全程距离，忽略缺失值。
     *
     * @param distance 累计距离采样，单位米
     * @return 全程距离，无有效值时为 0
     */
    private double maximumDistance(ArrayNode distance) {
        double totalDistance = 0;
        for (JsonNode value : distance) {
            if (value.isNumber()) {
                totalDistance = Math.max(totalDistance, value.asDouble());
            }
        }

        return totalDistance;
    }

    /**
     * 以全程距离的中点分前后半程，比较速度/心率的平均效率。
     *
     * @param distance 累计距离采样，单位米
     * @param speed 速度采样，单位米/秒
     * @param heartRate 心率采样，单位 bpm
     * @param totalDistance 全程距离，单位米
     * @return 效率下降百分比；任一半程不足 30 个有效样本时为 null
     */
    private Double calculateHeartRateDrift(
            ArrayNode distance, ArrayNode speed, ArrayNode heartRate, double totalDistance) {
        List<Double> first = new ArrayList<>();
        List<Double> second = new ArrayList<>();
        for (int i = 0; i < distance.size(); i++) {
            Double sampleDistance = numberAt(distance, i);
            Double sampleSpeed = numberAt(speed, i);
            Double sampleHeartRate = numberAt(heartRate, i);
            if (sampleDistance == null
                    || sampleSpeed == null
                    || sampleHeartRate == null
                    || sampleSpeed < .8
                    || sampleHeartRate <= 0) {
                continue;
            }
            if (sampleDistance <= totalDistance / 2) {
                first.add(sampleSpeed / sampleHeartRate);
            } else {
                second.add(sampleSpeed / sampleHeartRate);
            }
        }
        Double drift = null;
        if (first.size() >= 30 && second.size() >= 30) {
            double firstHalfEfficiency = average(first);
            drift =
                    firstHalfEfficiency == 0
                            ? null
                            : (firstHalfEfficiency - average(second)) / firstHalfEfficiency * 100;
        }
        return drift;
    }

    /**
     * 按配速变异系数与停顿比例推测训练类型；显式分支保留原有判断优先级。
     *
     * @param paceCv 配速变异系数，单位百分比；样本不足时为 null
     * @param stopRatio 停顿比例，范围 0～1；无有效速度时为 null
     * @return 面向前端展示的训练类型说明
     */
    private String classifyTrainingType(Double paceCv, Double stopRatio) {
        if (paceCv == null) {
            return "数据不足";
        }
        if (paceCv < 6 && value(stopRatio) < .04) {
            return "稳定跑";
        }
        if (paceCv >= 14 || value(stopRatio) >= .08) {
            return "变速 / 间歇特征";
        }
        return "节奏变化跑";
    }

    /**
     * 按 floor(距离/1000)+1 分公里汇总，各指标分别统计有效样本。
     *
     * @param distance 累计距离采样，单位米
     * @param speed 速度采样，单位米/秒
     * @param heartRate 心率采样，单位 bpm
     * @param altitude 海拔采样，单位米
     * @param totalDistance 全程距离，单位米
     * @return 按公里编号递增的统计数组
     */
    private ArrayNode buildKilometerSplits(
            ArrayNode distance,
            ArrayNode speed,
            ArrayNode heartRate,
            ArrayNode altitude,
            double totalDistance) {
        Map<Integer, Bucket> buckets = new TreeMap<>();
        int lastKm = (int) Math.ceil(totalDistance / 1000);
        for (int i = 0; i < distance.size(); i++) {
            Double d = numberAt(distance, i);
            if (d == null) {
                continue;
            }
            int km = (int) Math.floor(d / 1000) + 1;
            if (km > lastKm) {
                continue;
            }
            Bucket bucket = buckets.computeIfAbsent(km, ignored -> new Bucket());
            Double s = numberAt(speed, i);
            Double hr = numberAt(heartRate, i);
            Double alt = numberAt(altitude, i);
            if (s != null && s > .8) {
                bucket.speeds.add(s);
            }
            if (hr != null) {
                bucket.heartRates.add(hr);
            }
            if (alt != null) {
                bucket.altitudes.add(alt);
            }
        }
        ArrayNode splits = JsonNodeFactory.instance.arrayNode();
        buckets.forEach(
                (km, b) -> {
                    ObjectNode split = splits.addObject();
                    split.put("kilometer", km);
                    put(
                            split,
                            "pace_s_per_km",
                            b.speeds.isEmpty() ? null : 1000 / average(b.speeds));
                    put(split, "average_heart_rate", avgOrNull(b.heartRates));
                    put(split, "average_altitude_m", avgOrNull(b.altitudes));
                });
        return splits;
    }

    /**
     * 优先使用增强采样数组；数组为空时回退到普通采样字段。
     *
     * @param parent 包含采样字段的父 JSON 对象
     * @param first 首选采样字段名
     * @param second 回退采样字段名
     * @return 非空的增强采样数组，或普通采样数组；两者均不可用时为空数组
     */
    private ArrayNode preferred(JsonNode parent, String first, String second) {
        ArrayNode a = array(parent.path(first));
        return a.isEmpty() ? array(parent.path(second)) : a;
    }

    /**
     * 安全读取数组节点；类型不匹配时返回空数组。
     *
     * @param node 待读取或写入的 JSON 节点
     * @return 原数组节点；输入不是数组时返回新建的空数组
     */
    private ArrayNode array(JsonNode node) {
        return node instanceof ArrayNode a ? a : JsonNodeFactory.instance.arrayNode();
    }

    /**
     * 读取同索引的可空采样值，数组不足时返回 null。
     *
     * @param a 按采样点顺序排列的 JSON 数组
     * @param i 采样点索引，从 0 开始
     * @return 该采样点的数值；索引超出数组长度或值非数值时为 null
     */
    private Double numberAt(ArrayNode a, int i) {
        return i < a.size() ? JsonValues.nullableNumber(a.get(i)) : null;
    }

    /**
     * 计算样本算术平均值；空集合在此底层方法中返回 0。
     *
     * @param values 有效数值样本集合
     * @return 算术平均值，空集合返回 0
     */
    private double average(List<Double> values) {
        return values.stream().mapToDouble(Double::doubleValue).average().orElse(0);
    }

    /**
     * 计算有效样本平均值；没有样本时返回 null。
     *
     * @param values 有效数值样本集合
     * @return 算术平均值，空集合返回 null
     */
    private Double avgOrNull(List<Double> values) {
        return values.isEmpty() ? null : average(values);
    }

    /**
     * 计算总体标准差（除以样本数 N），与原 Python 的 pstdev 口径一致。
     *
     * @param values 有效数值样本集合
     * @return 总体标准差
     */
    private double deviation(List<Double> values) {
        double mean = average(values);
        return Math.sqrt(
                values.stream().mapToDouble(v -> Math.pow(v - mean, 2)).average().orElse(0));
    }

    /**
     * 仅在规则比较时将可空比例回退为 0。
     *
     * @param v 可空的数值或负荷比
     * @return 原数值；null 时返回 0
     */
    private double value(Double v) {
        return v == null ? 0 : v;
    }

    /**
     * 输出可空数值；null 或非有限值写为 JSON null，否则按当前服务口径舍入。
     *
     * @param node 待读取或写入的 JSON 节点
     * @param field 待读取或写入的 JSON 字段名
     * @param value 待转换、舍入或校验的值
     */
    private void put(ObjectNode node, String field, Double value) {
        if (value == null || !Double.isFinite(value)) {
            node.putNull(field);
        } else {
            node.put(field, JsonValues.round(value, 1));
        }
    }

    /** 单个公里分段的有效采样集合；速度、心率、海拔分别维护，避免缺失值参与平均。 */
    private static final class Bucket {
        private final List<Double> speeds = new ArrayList<>();
        private final List<Double> heartRates = new ArrayList<>();
        private final List<Double> altitudes = new ArrayList<>();
    }
}
