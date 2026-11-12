package dev.runningatlas.api.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.nio.file.Path;
import java.util.List;

/**
 * 类型安全的应用配置。
 *
 * <p>{@code @ConfigurationProperties} 将 running-webgis 前缀配置绑定到不可变 record； 紧凑构造器校验数据目录，并复制允许来源列表。
 *
 * @param dataDirectory 派生数据目录，可由环境变量覆盖
 * @param allowedOrigins 允许跨域请求的前端来源列表
 */
@ConfigurationProperties(prefix = "running-webgis")
public record RunningWebgisProperties(String dataDirectory, List<String> allowedOrigins) {
    /**
     * 在配置绑定时校验必填目录，并复制来源列表，避免外部修改配置集合。
     *
     * @param dataDirectory 派生数据目录，不能为 null 或空白字符串
     * @param allowedOrigins 允许的跨域来源；null 转换为空列表
     * @throws IllegalArgumentException 数据目录为空时阻止应用启动
     */
    public RunningWebgisProperties {
        if (dataDirectory == null || dataDirectory.isBlank()) {
            throw new IllegalArgumentException("running-webgis.data-directory must not be blank");
        }
        allowedOrigins = allowedOrigins == null ? List.of() : List.copyOf(allowedOrigins);
    }

    /**
     * 相对 JVM 启动目录解析绝对路径，并消除路径中的冗余片段。
     *
     * @return 规范化后的绝对数据目录
     */
    public Path resolvedDataDirectory() {
        return Path.of(dataDirectory).toAbsolutePath().normalize();
    }
}
