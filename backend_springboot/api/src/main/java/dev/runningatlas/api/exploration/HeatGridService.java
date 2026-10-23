package dev.runningatlas.api.exploration;

import dev.runningatlas.api.activity.ActivityRepository;
import dev.runningatlas.api.common.ApiException;
import dev.runningatlas.api.common.DataReadinessService;
import dev.runningatlas.api.common.JsonValues;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.JsonNodeFactory;
import tools.jackson.databind.node.ObjectNode;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * 空间探索业务层：筛选预计算网格中的活动，并组装 GeoJSON 点要素。
 *
 * <p>请求中不解析 FIT，也不重新进行空间网格计算；网格由 Python 离线生成。
 */
@Service
public class HeatGridService {
    private final ActivityRepository repository;
    private final DataReadinessService readiness;

    /**
     * 通过构造器接收依赖；Spring 创建组件时自动提供这些实例，无需手工 new。
     *
     * @param repository 只读派生文件访问层，由 Spring 注入
     * @param readiness 统一数据就绪检查服务，由 Spring 注入
     */
    public HeatGridService(ActivityRepository repository, DataReadinessService readiness) {
        this.repository = repository;
        this.readiness = readiness;
    }

    /**
     * 按可选日期及最少经过次数筛选网格，返回 GeoJSON FeatureCollection。
     *
     * @param start 开始日期，包含当天；可选参数允许 null
     * @param end 结束日期，包含当天；可选参数允许 null
     * @param minVisits 网格最少经过次数，范围 1 至 100
     * @return 包含网格中心点、经过次数、累计距离及首末日期的 FeatureCollection
     * @throws ApiException 日期颠倒或最少次数越界时为 422；数据未就绪时为 503
     */
    public ObjectNode query(LocalDate start, LocalDate end, int minVisits) {
        readiness.assertReady();
        if (start != null && end != null && start.isAfter(end)) {
            throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "起始日期不能晚于结束日期。");
        }
        if (minVisits < 1 || minVisits > 100) {
            throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "min_visits 必须在 1 到 100 之间。");
        }
        ObjectNode source = repository.spatialGrid();
        ArrayNode features = JsonNodeFactory.instance.arrayNode();
        for (JsonNode cell : source.path("cells")) {
            List<JsonNode> matches = new ArrayList<>();
            for (JsonNode activity : cell.path("activities")) {
                String text = JsonValues.text(activity, "date");
                if (text == null) {
                    continue;
                }
                LocalDate date = LocalDate.parse(text);
                if ((start == null || !date.isBefore(start))
                        && (end == null || !date.isAfter(end))) {
                    matches.add(activity);
                }
            }
            if (matches.size() < minVisits) {
                continue;
            }
            ObjectNode feature = features.addObject();
            feature.put("type", "Feature");
            ArrayNode coordinates =
                    feature.putObject("geometry").put("type", "Point").putArray("coordinates");
            // GeoJSON 坐标顺序是 [经度, 纬度]，与部分地图 SDK 的参数顺序不同。
            coordinates.add(JsonValues.number(cell, "longitude"));
            coordinates.add(JsonValues.number(cell, "latitude"));
            ObjectNode props = feature.putObject("properties");
            // visits 是筛选后关联活动条目的数量，不是 GPS 采样点数量。
            props.put("cell_id", JsonValues.text(cell, "cell_id"));
            props.put("visits", matches.size());
            props.put(
                    "distance_m",
                    JsonValues.round(
                            matches.stream()
                                    .mapToDouble(a -> JsonValues.number(a, "distance_m"))
                                    .sum(),
                            1));
            Comparator<JsonNode> byDate = Comparator.comparing(a -> JsonValues.text(a, "date"));
            props.put(
                    "first_date",
                    JsonValues.text(matches.stream().min(byDate).orElseThrow(), "date"));
            props.put(
                    "last_date",
                    JsonValues.text(matches.stream().max(byDate).orElseThrow(), "date"));
        }
        ObjectNode result = JsonNodeFactory.instance.objectNode();
        result.put("type", "FeatureCollection");
        result.put("cell_size_m", source.path("cell_size_m").asInt());
        result.put("feature_count", features.size());
        result.set("features", features);
        return result;
    }
}
