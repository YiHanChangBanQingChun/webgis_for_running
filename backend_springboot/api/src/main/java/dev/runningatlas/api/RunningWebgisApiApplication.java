package dev.runningatlas.api;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

/**
 * Spring Boot 启动入口。
 *
 * <p>{@code @SpringBootApplication} 启用自动配置与当前包下的组件扫描； {@code @ConfigurationPropertiesScan}
 * 注册类型安全的配置对象。
 */
@SpringBootApplication
@ConfigurationPropertiesScan
public class RunningWebgisApiApplication {

    /**
     * 启动 Spring 容器、自动配置和嵌入式 Web 服务。
     *
     * @param args 命令行启动参数
     */
    public static void main(String[] args) {
        SpringApplication.run(RunningWebgisApiApplication.class, args);
    }
}
