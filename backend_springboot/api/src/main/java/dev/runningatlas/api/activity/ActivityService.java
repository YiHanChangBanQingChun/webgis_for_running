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

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * 活动查询业务层：执行筛选、排序、分页和详情查找。
 *
 * <p>{@code @Service} 将实例交给 Spring 容器管理。通过构造器接收 Repository 和就绪检查服务，
 * 无需在方法中手工创建依赖；距离参数使用千米，派生文件中的距离使用米。
 */
@Service
public class ActivityService {
    private final ActivityRepository repository;
    private final DataReadinessService readiness;

    /**
     * 通过构造器接收依赖；Spring 创建组件时自动提供这些实例，无需手工 new。
     *
     * @param repository 只读派生文件访问层，由 Spring 注入
     * @param readiness 统一数据就绪检查服务，由 Spring 注入
     */
    public ActivityService(ActivityRepository repository, DataReadinessService readiness) {
        this.repository = repository;
        this.readiness = readiness;
    }

    /**
     * 按日期、运动类型、GPS 和距离筛选，再排序并返回分页结果；total 为分页前数量。
     *
     * @param start 开始日期，包含当天；可选参数允许 null
     * @param end 结束日期，包含当天；可选参数允许 null
     * @param sport 运动类型编码；null 表示不限
     * @param hasGps 是否有 GPS；null 表示不限
     * @param minKm 最小距离，单位千米；null 表示不限
     * @param maxKm 最大距离，单位千米；null 表示不限
     * @param sort 活动排序规则
     * @param offset 跳过的记录数，从 0 开始
     * @param limit 本页最多返回的记录数
     * @return 含 total（筛选后总数）和 items（当前页活动）的对象
     * @throws ApiException 日期或距离上下限颠倒时为 422；数据未就绪时为 503
     */
    public ObjectNode list(
            LocalDate start,
            LocalDate end,
            String sport,
            Boolean hasGps,
            Double minKm,
            Double maxKm,
            Sort sort,
            int offset,
            int limit) {
        readiness.assertReady();
        if (start != null && end != null && start.isAfter(end)) {
            throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "起始日期不能晚于结束日期。");
        }
        if (minKm != null && maxKm != null && minKm > maxKm) {
            throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "最小距离不能大于最大距离。");
        }
        List<JsonNode> rows = new ArrayList<>();
        // 每个可选条件都使用“未提供，或满足条件”的写法；最终所有条件必须同时成立。
        for (JsonNode row : repository.activities()) {
            String dateText = JsonValues.text(row, "date");
            LocalDate date = dateText == null ? null : LocalDate.parse(dateText);
            boolean match =
                    (start == null || date != null && !date.isBefore(start))
                            && (end == null || date != null && !date.isAfter(end))
                            && (sport == null || sport.equals(JsonValues.text(row, "sport")))
                            && (hasGps == null || hasGps == row.path("has_gps").asBoolean(false))
                            && (minKm == null
                                    || JsonValues.number(row, "distance_m") >= minKm * 1000)
                            && (maxKm == null
                                    || JsonValues.number(row, "distance_m") <= maxKm * 1000);
            if (match) {
                rows.add(row);
            }
        }

        // 枚举决定比较字段，是否 reversed 决定升序或降序。
        Comparator<JsonNode> comparator =
                switch (sort) {
                    case DISTANCE_ASC, DISTANCE_DESC ->
                            Comparator.comparingDouble(row -> JsonValues.number(row, "distance_m"));
                    case DATE_ASC, DATE_DESC ->
                            Comparator.comparing(
                                    row -> JsonValues.text(row, "start_time"),
                                    Comparator.nullsFirst(String::compareTo));
                };
        if (sort == Sort.DATE_DESC || sort == Sort.DISTANCE_DESC) {
            comparator = comparator.reversed();
        }
        rows.sort(comparator);
        // 先排序再分页；分页起止位置不能超过筛选后的数量。
        int from = Math.min(offset, rows.size());
        int to = Math.min(from + limit, rows.size());
        ArrayNode items = JsonNodeFactory.instance.arrayNode();
        rows.subList(from, to).forEach(items::add);
        ObjectNode result = JsonNodeFactory.instance.objectNode();
        result.put("total", rows.size());
        result.set("items", items);
        return result;
    }

    /**
     * 读取预计算运动日历；不在请求中重新遍历 FIT 文件。
     *
     * @return 预计算的运动日历数组
     */
    public ArrayNode calendar() {
        readiness.assertReady();
        return repository.calendar();
    }

    /**
     * 按活动 ID 查询摘要；未找到时返回 404 业务异常。
     *
     * @param id 活动 ID
     * @return ID 对应的活动摘要；不能修改其中的缓存字段
     * @throws ApiException 活动不存在时为 404；数据未就绪时为 503
     */
    public JsonNode detail(String id) {
        readiness.assertReady();
        for (JsonNode row : repository.activities()) {
            if (id.equals(JsonValues.text(row, "id"))) {
                return row;
            }
        }
        throw new ApiException(HttpStatus.NOT_FOUND, "未找到该活动。");
    }

    /**
     * 读取指定活动的轨迹 GeoJSON；缺失时返回 404。
     *
     * @param id 活动 ID
     * @return 指定活动的 GeoJSON 对象
     * @throws ApiException ID 不合法时为 400；轨迹不存在时为 404；数据未就绪时为 503
     */
    public ObjectNode track(String id) {
        readiness.assertReady();
        return repository.track(id);
    }

    /** 活动排序枚举，将外部字符串限制为四种支持的排序方式。 */
    public enum Sort {
        DATE_DESC,
        DATE_ASC,
        DISTANCE_DESC,
        DISTANCE_ASC;

        /**
         * 将接口排序字符串转换为枚举，非法值转换为 422 业务异常。
         *
         * @param value 前端排序字符串，例如 date_desc
         * @return 受支持的排序枚举
         */
        public static Sort parse(String value) {
            try {
                return valueOf(value.toUpperCase());
            } catch (IllegalArgumentException exception) {
                throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "sort 参数不合法。");
            }
        }
    }
}
