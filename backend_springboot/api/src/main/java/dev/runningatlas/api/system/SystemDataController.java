package dev.runningatlas.api.system;

import dev.runningatlas.api.activity.ActivityRepository;
import dev.runningatlas.api.common.DataReadinessService;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.JsonNodeFactory;
import tools.jackson.databind.node.ObjectNode;

/**
 * 系统数据接口：返回业务健康状态、数据质量报告与运动员配置。
 *
 * <p>业务健康接口会检查数据是否就绪；这与仅检查进程存活的 Actuator 健康接口不同。
 */
@RestController
@RequestMapping("/api")
public class SystemDataController {
    private final ActivityRepository repository;
    private final DataReadinessService readiness;

    /**
     * 通过构造器接收依赖；Spring 创建组件时自动提供这些实例，无需手工 new。
     *
     * @param repository 只读派生文件访问层，由 Spring 注入
     * @param readiness 统一数据就绪检查服务，由 Spring 注入
     */
    public SystemDataController(ActivityRepository repository, DataReadinessService readiness) {
        this.repository = repository;
        this.readiness = readiness;
    }

    /**
     * 检查派生数据是否就绪；就绪返回 200，否则返回 503，并附 readiness。
     *
     * @return 携带明确 HTTP 状态码及 JSON 内容的响应
     */
    @GetMapping("/health")
    public ResponseEntity<JsonNode> health() {
        ObjectNode state = readiness.readiness();
        boolean ready = state.path("api_ready").asBoolean(false);
        ObjectNode body = JsonNodeFactory.instance.objectNode();
        body.put("status", ready ? "ok" : "not_ready");
        body.set("readiness", state);
        return ResponseEntity.status(ready ? HttpStatus.OK : HttpStatus.SERVICE_UNAVAILABLE)
                .body(body);
    }

    /**
     * 读取离线导入质量报告，包含 API 就绪标记与数据覆盖信息。
     *
     * @return 完整离线质量报告，不只包含 readiness 字段
     */
    @GetMapping("/quality-report")
    public JsonNode qualityReport() {
        return repository.qualityReport();
    }

    /**
     * 读取运动员配置；尚未同步时抛出 404。
     *
     * @return 已同步的运动员配置对象
     */
    @GetMapping("/athlete-profile")
    public JsonNode athleteProfile() {
        return repository.athleteProfile();
    }
}
