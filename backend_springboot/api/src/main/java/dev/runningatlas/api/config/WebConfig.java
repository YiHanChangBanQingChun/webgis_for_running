package dev.runningatlas.api.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/** Restricts cross-origin access to the configured frontend development origins. */
@Configuration
public class WebConfig implements WebMvcConfigurer {
    private final RunningWebgisProperties properties;

    public WebConfig(RunningWebgisProperties properties) {
        this.properties = properties;
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins(properties.allowedOrigins().toArray(String[]::new))
                .allowedMethods("GET")
                .allowedHeaders("*");
    }
}
