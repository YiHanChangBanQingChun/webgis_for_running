package dev.runningatlas.api.exploration;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import tools.jackson.databind.JsonNode;

import java.time.LocalDate;

/**
 * 空间探索控制器：提供预计算网格的 GeoJSON 查询接口。
 *
 * <p>Spring 将日期、次数等查询字符串转换为方法参数，筛选与响应组装由 Service 完成。
 */
@RestController
@RequestMapping("/api/map")
public class HeatGridController {
    private final HeatGridService service;

    /**
     * 通过构造器接收依赖；Spring 创建组件时自动提供这些实例，无需手工 new。
     *
     * @param service 当前接口对应的业务服务，由 Spring 注入
     */
    public HeatGridController(HeatGridService service) {
        this.service = service;
    }

    /**
     * 按可选日期及最少经过次数筛选网格，返回 GeoJSON FeatureCollection。
     *
     * @param start 开始日期，包含当天；可选参数允许 null
     * @param end 结束日期，包含当天；可选参数允许 null
     * @param minVisits 网格最少经过次数，范围 1 至 100
     * @return 网格中心点组成的 GeoJSON FeatureCollection
     */
    @GetMapping("/heat-grid")
    public JsonNode query(
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
                    LocalDate start,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
                    LocalDate end,
            @RequestParam(name = "min_visits", defaultValue = "1") int minVisits) {
        return service.query(start, end, minVisits);
    }
}
