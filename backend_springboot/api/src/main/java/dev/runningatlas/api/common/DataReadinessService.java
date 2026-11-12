package dev.runningatlas.api.common;

import dev.runningatlas.api.activity.ActivityRepository;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import tools.jackson.databind.node.ObjectNode;

/**
 * 数据质量门禁：集中检查导入报告中的 readiness.api_ready。
 *
 * <p>数据尚未就绪时抛出 503，避免各业务服务重复实现质量判断。
 */
@Service
public class DataReadinessService {
    private final ActivityRepository repository;

    /**
     * 通过构造器接收依赖；Spring 创建组件时自动提供这些实例，无需手工 new。
     *
     * @param repository 只读派生文件访问层，由 Spring 注入
     */
    public DataReadinessService(ActivityRepository repository) {
        this.repository = repository;
    }

    /**
     * 读取质量报告的 readiness 对象；结构错误时抛出 500。
     *
     * @return 报告中共享的 readiness 节点，仅供读取
     * @throws ApiException 报告缺失时为 503；readiness 结构不正确时为 500
     */
    public ObjectNode readiness() {
        if (repository.qualityReport().path("readiness") instanceof ObjectNode object) {
            return object;
        }
        throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "质量报告缺少 readiness 对象。");
    }

    /**
     * 检查 api_ready 布尔标记，缺失时视为未就绪。
     *
     * @return 仅当 api_ready 为 true 时返回 true
     */
    public boolean isReady() {
        return readiness().path("api_ready").asBoolean(false);
    }

    /**
     * 要求数据已就绪，否则中止当前业务。
     *
     * @throws ApiException 数据未就绪时为 503；质量报告结构错误时为 500
     */
    public void assertReady() {
        if (!isReady()) {
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "数据质量尚未满足 API 启动条件。");
        }
    }
}
