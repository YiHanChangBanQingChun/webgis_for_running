package dev.runningatlas.api.activity;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Repository;

import dev.runningatlas.api.common.ApiException;
import dev.runningatlas.api.config.RunningWebgisProperties;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/**
 * Read-only gateway for every derived JSON/GeoJSON file.
 * The cache is automatically invalidated when file size or modification time changes.
 */
@Repository
public class ActivityRepository {
    private static final Pattern SAFE_ID = Pattern.compile("^[A-Za-z0-9_-]+$");
    private final Path dataDirectory;
    private final ObjectMapper objectMapper;
    private final Map<Path, CachedJson> cache = new ConcurrentHashMap<>();

    public ActivityRepository(RunningWebgisProperties properties, ObjectMapper objectMapper) {
        this.dataDirectory = properties.resolvedDataDirectory();
        this.objectMapper = objectMapper;
    }

    public ArrayNode activities() { return requireArray("activities.json", "派生活动数据不存在；请先运行 build_derived.py。"); }
    public ArrayNode calendar() { return requireArray("calendar.json", "日历数据不存在；请先运行 build_derived.py。"); }
    public ObjectNode qualityReport() { return requireObject(Path.of("import-report.json"), "质量报告不存在；请先运行 build_quality_report.py。", HttpStatus.SERVICE_UNAVAILABLE); }
    public ObjectNode spatialGrid() { return requireObject(Path.of("spatial-grid.json"), "空间网格不存在；请先运行 build_spatial_grid.py。", HttpStatus.SERVICE_UNAVAILABLE); }
    public ObjectNode athleteProfile() { return requireObject(Path.of("athlete-profile.json"), "运动员配置尚未同步。", HttpStatus.NOT_FOUND); }

    public ObjectNode track(String activityId) {
        if (activityId == null || !SAFE_ID.matcher(activityId).matches()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "活动 ID 格式不合法。");
        }
        return requireObject(Path.of("tracks", activityId + ".geojson"), "该活动没有可用 GPS 轨迹。", HttpStatus.NOT_FOUND);
    }

    private ArrayNode requireArray(String filename, String message) {
        JsonNode node = read(dataDirectory.resolve(filename), message, HttpStatus.SERVICE_UNAVAILABLE);
        if (node instanceof ArrayNode array) return array;
        throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, filename + " 的顶层结构应为 JSON 数组。");
    }

    private ObjectNode requireObject(Path relative, String message, HttpStatus status) {
        JsonNode node = read(dataDirectory.resolve(relative), message, status);
        if (node instanceof ObjectNode object) return object;
        throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, relative + " 的顶层结构应为 JSON 对象。");
    }

    private JsonNode read(Path path, String missingMessage, HttpStatus missingStatus) {
        Path normalized = path.toAbsolutePath().normalize();
        if (!normalized.startsWith(dataDirectory)) throw new ApiException(HttpStatus.BAD_REQUEST, "非法数据文件路径。");
        if (!Files.isRegularFile(normalized)) throw new ApiException(missingStatus, missingMessage);
        try {
            FileTime modifiedAt = Files.getLastModifiedTime(normalized);
            long size = Files.size(normalized);
            CachedJson cached = cache.get(normalized);
            if (cached != null && cached.modifiedAt.equals(modifiedAt) && cached.size == size) return cached.value;
            try (InputStream input = Files.newInputStream(normalized)) {
                JsonNode value = objectMapper.readTree(input);
                cache.put(normalized, new CachedJson(modifiedAt, size, value));
                return value;
            }
        } catch (IOException exception) {
            throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "读取派生数据失败：" + normalized.getFileName());
        }
    }

    private record CachedJson(FileTime modifiedAt, long size, JsonNode value) { }
}
