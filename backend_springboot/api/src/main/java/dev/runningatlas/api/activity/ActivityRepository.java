package dev.runningatlas.api.activity;

import dev.runningatlas.api.common.ApiException;
import dev.runningatlas.api.config.RunningWebgisProperties;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Repository;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;

/**
 * 派生数据的只读访问层；当前 Repository 读取文件，并非数据库。
 *
 * <p>统一封装 JSON 解析、路径校验和缓存。文件大小或修改时间改变时重新读取。 缓存中的 JSON 节点会被共享，调用方应只读，修改结果时应新建响应对象。
 */
@Repository
public class ActivityRepository {
    private static final Pattern SAFE_ID = Pattern.compile("^[A-Za-z0-9_-]+$");
    private final Path dataDirectory;
    private final ObjectMapper objectMapper;
    private final Map<Path, CachedJson> cache = new ConcurrentHashMap<>();

    /**
     * 通过构造器接收依赖；Spring 创建组件时自动提供这些实例，无需手工 new。
     *
     * @param properties 已绑定并校验的应用配置
     * @param objectMapper Spring 配置的 Jackson JSON 解析器
     */
    public ActivityRepository(RunningWebgisProperties properties, ObjectMapper objectMapper) {
        this.dataDirectory = properties.resolvedDataDirectory();
        this.objectMapper = objectMapper;
    }

    /**
     * 读取活动摘要数组，供上层进行筛选与聚合。
     *
     * @return 活动摘要数组；节点来自只读缓存
     */
    public ArrayNode activities() {
        return requireArray("activities.json", "派生活动数据不存在；请先运行 build_derived.py。");
    }

    /**
     * 读取预计算运动日历；不在请求中重新遍历 FIT 文件。
     *
     * @return 按日期组织的预计算日历数组
     */
    public ArrayNode calendar() {
        return requireArray("calendar.json", "日历数据不存在；请先运行 build_derived.py。");
    }

    /**
     * 读取离线导入质量报告，包含 API 就绪标记与数据覆盖信息。
     *
     * @return 包含 readiness 等字段的导入质量报告
     */
    public ObjectNode qualityReport() {
        return requireObject(
                Path.of("import-report.json"),
                "质量报告不存在；请先运行 build_quality_report.py。",
                HttpStatus.SERVICE_UNAVAILABLE);
    }

    /**
     * 读取预计算的空间网格对象。
     *
     * @return 包含 cell_size_m 和 cells 的空间网格数据
     */
    public ObjectNode spatialGrid() {
        return requireObject(
                Path.of("spatial-grid.json"),
                "空间网格不存在；请先运行 build_spatial_grid.py。",
                HttpStatus.SERVICE_UNAVAILABLE);
    }

    /**
     * 读取运动员配置；尚未同步时抛出 404。
     *
     * @return 离线同步的运动员配置对象
     */
    public ObjectNode athleteProfile() {
        return requireObject(Path.of("athlete-profile.json"), "运动员配置尚未同步。", HttpStatus.NOT_FOUND);
    }

    /**
     * 读取指定活动的轨迹 GeoJSON；缺失时返回 404。
     *
     * @param activityId 活动 ID，只允许字母、数字、下划线和连字符
     * @return 指定活动的 GeoJSON 对象
     * @throws ApiException ID 不合法时为 400；轨迹文件不存在时为 404
     */
    public ObjectNode track(String activityId) {
        if (activityId == null || !SAFE_ID.matcher(activityId).matches()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "活动 ID 格式不合法。");
        }
        return requireObject(
                Path.of("tracks", activityId + ".geojson"),
                "该活动没有可用 GPS 轨迹。",
                HttpStatus.NOT_FOUND);
    }

    /**
     * 读取并校验 JSON 顶层为数组；格式不符时抛出 500。
     *
     * @param filename 数据文件名
     * @param message 可向前端展示的错误说明
     * @return 通过顶层类型校验的 JSON 数组
     */
    private ArrayNode requireArray(String filename, String message) {
        JsonNode node =
                read(dataDirectory.resolve(filename), message, HttpStatus.SERVICE_UNAVAILABLE);
        if (node instanceof ArrayNode array) {
            return array;
        }
        throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, filename + " 的顶层结构应为 JSON 数组。");
    }

    /**
     * 读取并校验 JSON 顶层为对象；调用方决定缺失文件的 HTTP 状态。
     *
     * @param relative 相对派生数据目录的文件路径
     * @param message 可向前端展示的错误说明
     * @param status 响应 HTTP 状态码
     * @return 通过顶层类型校验的 JSON 对象
     */
    private ObjectNode requireObject(Path relative, String message, HttpStatus status) {
        JsonNode node = read(dataDirectory.resolve(relative), message, status);
        if (node instanceof ObjectNode object) {
            return object;
        }
        throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, relative + " 的顶层结构应为 JSON 对象。");
    }

    /**
     * 规范化文件路径并检查缓存；使用 try-with-resources 保证输入流关闭。
     *
     * @param path 待读取的数据文件路径
     * @param missingMessage 文件不存在时向前端返回的说明
     * @param missingStatus 文件不存在时使用的 HTTP 状态
     * @return 缓存命中的节点，或从文件重新解析得到的节点；调用方不可修改
     */
    private JsonNode read(Path path, String missingMessage, HttpStatus missingStatus) {
        Path normalized = path.toAbsolutePath().normalize();
        // 防止相对路径中的 ../ 越出配置的数据目录；活动 ID 还会经过白名单校验。
        if (!normalized.startsWith(dataDirectory)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "非法数据文件路径。");
        }
        if (!Files.isRegularFile(normalized)) {
            throw new ApiException(missingStatus, missingMessage);
        }
        try {
            FileTime modifiedAt = Files.getLastModifiedTime(normalized);
            long size = Files.size(normalized);
            CachedJson cached = cache.get(normalized);
            // 同时比较修改时间与字节数，而不是每次请求都重新读取和解析整个文件。
            if (cached != null && cached.modifiedAt.equals(modifiedAt) && cached.size == size) {
                return cached.value;
            }
            try (InputStream input = Files.newInputStream(normalized)) {
                JsonNode value = objectMapper.readTree(input);
                cache.put(normalized, new CachedJson(modifiedAt, size, value));
                return value;
            }
        } catch (IOException exception) {
            throw new ApiException(
                    HttpStatus.INTERNAL_SERVER_ERROR, "读取派生数据失败：" + normalized.getFileName());
        }
    }

    /** 缓存快照：同时保存文件修改时间、字节数和解析后的 JSON 节点。 */
    private record CachedJson(FileTime modifiedAt, long size, JsonNode value) {}
}
