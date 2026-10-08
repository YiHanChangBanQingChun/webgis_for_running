package dev.runningatlas.api.common;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import dev.runningatlas.api.activity.ActivityRepository;
import tools.jackson.databind.node.ObjectNode;

/** Centralizes the quality gate applied before serving derived activity data. */
@Service
public class DataReadinessService {
    private final ActivityRepository repository;

    public DataReadinessService(ActivityRepository repository) { this.repository = repository; }

    public ObjectNode readiness() {
        if (repository.qualityReport().path("readiness") instanceof ObjectNode object) return object;
        throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "质量报告缺少 readiness 对象。");
    }

    public boolean isReady() { return readiness().path("api_ready").asBoolean(false); }

    public void assertReady() {
        if (!isReady()) throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "数据质量尚未满足 API 启动条件。");
    }
}
