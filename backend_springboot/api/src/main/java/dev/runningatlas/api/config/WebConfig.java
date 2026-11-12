package dev.runningatlas.api.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Spring MVC 跨域配置。
 *
 * <p>实现 WebMvcConfigurer，只扩展 CORS 规则，不替换 MVC 自动配置。 配置仅允许指定前端来源向 API 路径发起 GET 请求。
 */
@Configuration
public class WebConfig implements WebMvcConfigurer {
    private final RunningWebgisProperties properties;

    /**
     * 通过构造器接收依赖；Spring 创建组件时自动提供这些实例，无需手工 new。
     *
     * @param properties 已绑定并校验的应用配置
     */
    public WebConfig(RunningWebgisProperties properties) {
        this.properties = properties;
    }

    /**
     * 为 API 路径注册来源、方法与请求头的跨域规则。
     *
     * @param registry Spring MVC 提供的 CORS 规则注册器
     */
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins(properties.allowedOrigins().toArray(String[]::new))
                .allowedMethods("GET")
                .allowedHeaders("*");
    }
}
