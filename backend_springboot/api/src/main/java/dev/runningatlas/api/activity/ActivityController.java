package dev.runningatlas.api.activity;

import dev.runningatlas.api.common.ApiException;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import tools.jackson.databind.JsonNode;

import java.time.LocalDate;

/**
 * 活动查询控制器：负责 URL 路由、请求参数绑定和输入校验。
 *
 * <p>{@code @RestController} 使返回对象被序列化为 JSON；类上的路径与方法上的路径组合成完整 URL。 业务筛选交给 Service，控制器不直接读取文件。
 */
@RestController
@RequestMapping("/api")
public class ActivityController {
    private final ActivityService service;
    private final ActivityInsightsService insights;

    /**
     * 通过构造器接收依赖；Spring 创建组件时自动提供这些实例，无需手工 new。
     *
     * @param service 当前接口对应的业务服务，由 Spring 注入
     * @param insights 轨迹洞察计算服务，由 Spring 注入
     */
    public ActivityController(ActivityService service, ActivityInsightsService insights) {
        this.service = service;
        this.insights = insights;
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
     * @return 含 total 和 items 的分页响应
     * @throws ApiException 分页、距离或排序参数不合法时为 422
     */
    @GetMapping("/activities")
    public JsonNode list(
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
                    LocalDate start,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
                    LocalDate end,
            @RequestParam(required = false) String sport,
            @RequestParam(name = "has_gps", required = false) Boolean hasGps,
            @RequestParam(name = "min_distance_km", required = false) Double minKm,
            @RequestParam(name = "max_distance_km", required = false) Double maxKm,
            @RequestParam(defaultValue = "date_desc") String sort,
            @RequestParam(defaultValue = "0") int offset,
            @RequestParam(defaultValue = "100") int limit) {
        // required=false 的包装类型允许 null；例如 hasGps=null 表示不按 GPS 筛选。
        // name 指定 URL 参数名，保留旧接口的下划线命名；Java 变量仍使用驼峰命名。
        if (offset < 0 || limit < 1 || limit > 576) {
            throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "offset 或 limit 超出允许范围。");
        }
        if (minKm != null && minKm < 0 || maxKm != null && maxKm < 0) {
            throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "距离不能为负数。");
        }
        return service.list(
                start,
                end,
                sport,
                hasGps,
                minKm,
                maxKm,
                ActivityService.Sort.parse(sort),
                offset,
                limit);
    }

    /**
     * 读取预计算运动日历；不在请求中重新遍历 FIT 文件。
     *
     * @return 预计算的运动日历数组
     */
    @GetMapping("/calendar")
    public JsonNode calendar() {
        return service.calendar();
    }

    /**
     * 按活动 ID 查询摘要；未找到时返回 404 业务异常。
     *
     * @param id 活动 ID
     * @return 指定活动的摘要对象
     */
    @GetMapping("/activities/{id}")
    public JsonNode detail(@PathVariable String id) {
        return service.detail(id);
    }

    /**
     * 读取指定活动的轨迹 GeoJSON；缺失时返回 404。
     *
     * @param id 活动 ID
     * @return 指定活动的 GeoJSON 轨迹对象
     */
    @GetMapping("/activities/{id}/track")
    public JsonNode track(@PathVariable String id) {
        return service.track(id);
    }

    /**
     * 返回指定活动的自动训练洞察及分公里统计。
     *
     * @param id 活动 ID
     * @return 含配速波动、心率漂移、训练类型和分公里统计的对象
     */
    @GetMapping("/activities/{id}/insights")
    public JsonNode insights(@PathVariable String id) {
        return insights.analyze(id);
    }
}
