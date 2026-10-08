package dev.runningatlas.api.config;

import java.nio.file.Path;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** Type-safe application configuration for the processed-data directory and CORS origins. */
@ConfigurationProperties(prefix = "running-webgis")
public record RunningWebgisProperties(String dataDirectory, List<String> allowedOrigins) {
    public RunningWebgisProperties {
        if (dataDirectory == null || dataDirectory.isBlank()) {
            throw new IllegalArgumentException("running-webgis.data-directory must not be blank");
        }
        allowedOrigins = allowedOrigins == null ? List.of() : List.copyOf(allowedOrigins);
    }

    /** Resolve a relative data path against the directory from which the JVM was started. */
    public Path resolvedDataDirectory() {
        return Path.of(dataDirectory).toAbsolutePath().normalize();
    }
}
