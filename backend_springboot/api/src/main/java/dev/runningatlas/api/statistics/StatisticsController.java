package dev.runningatlas.api.statistics;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import tools.jackson.databind.JsonNode;

import java.time.LocalDate;

/**
 * 统计接口控制器：将月份或日期范围参数交给统计服务。
 *
 * <p>日期使用 ISO 格式（YYYY-MM-DD）；返回字段保持与 Vue 前端及原 FastAPI 接口约定一致。
 */
@RestController
@RequestMapping("/api/stats")
public class StatisticsController {
    private final StatisticsService service;

    /**
     * 通过构造器接收依赖；Spring 创建组件时自动提供这些实例，无需手工 new。
     *
     * @param service 当前接口对应的业务服务，由 Spring 注入
     */
    public StatisticsController(StatisticsService service) {
        this.service = service;
    }

    /**
     * 统计指定月份未被排除的全部运动；保留各运动类型计数。
     *
     * @param month 月份，格式 YYYY-MM
     * @return 指定月份的训练摘要和运动类型计数
     */
    @GetMapping("/monthly")
    public JsonNode monthly(@RequestParam String month) {
        return service.monthly(month);
    }

    /**
     * 分析闭区间 [start, end] 内的正式跑步，并提前读取 27 天用于滚动负荷计算。
     *
     * @param start 开始日期，包含当天；HTTP 请求中必须提供
     * @param end 结束日期，包含当天；HTTP 请求中必须提供
     * @return 含 summary、daily 和 weekly 的区间统计对象
     */
    @GetMapping("/range")
    public JsonNode range(
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate start,
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate end) {
        return service.range(start, end);
    }
}
