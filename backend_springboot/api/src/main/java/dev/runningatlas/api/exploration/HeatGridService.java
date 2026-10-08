package dev.runningatlas.api.exploration;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import dev.runningatlas.api.activity.ActivityRepository;
import dev.runningatlas.api.common.ApiException;
import dev.runningatlas.api.common.DataReadinessService;
import dev.runningatlas.api.common.JsonValues;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.JsonNodeFactory;
import tools.jackson.databind.node.ObjectNode;

/** Filters the precomputed spatial exploration grid without doing GIS work inside a request. */
@Service
public class HeatGridService {
    private final ActivityRepository repository;
    private final DataReadinessService readiness;
    public HeatGridService(ActivityRepository repository, DataReadinessService readiness) { this.repository = repository; this.readiness = readiness; }

    public ObjectNode query(LocalDate start, LocalDate end, int minVisits) {
        readiness.assertReady();
        if (start != null && end != null && start.isAfter(end)) throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "起始日期不能晚于结束日期。");
        if (minVisits < 1 || minVisits > 100) throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "min_visits 必须在 1 到 100 之间。");
        ObjectNode source = repository.spatialGrid();
        ArrayNode features = JsonNodeFactory.instance.arrayNode();
        for (JsonNode cell : source.path("cells")) {
            List<JsonNode> matches = new ArrayList<>();
            for (JsonNode activity : cell.path("activities")) {
                String text = JsonValues.text(activity, "date"); if (text == null) continue;
                LocalDate date = LocalDate.parse(text);
                if ((start == null || !date.isBefore(start)) && (end == null || !date.isAfter(end))) matches.add(activity);
            }
            if (matches.size() < minVisits) continue;
            ObjectNode feature = features.addObject(); feature.put("type", "Feature");
            ArrayNode coordinates = feature.putObject("geometry").put("type", "Point").putArray("coordinates");
            coordinates.add(JsonValues.number(cell, "longitude")); coordinates.add(JsonValues.number(cell, "latitude"));
            ObjectNode props = feature.putObject("properties"); props.put("cell_id", JsonValues.text(cell, "cell_id")); props.put("visits", matches.size());
            props.put("distance_m", JsonValues.round(matches.stream().mapToDouble(a -> JsonValues.number(a, "distance_m")).sum(), 1));
            Comparator<JsonNode> byDate = Comparator.comparing(a -> JsonValues.text(a, "date"));
            props.put("first_date", JsonValues.text(matches.stream().min(byDate).orElseThrow(), "date"));
            props.put("last_date", JsonValues.text(matches.stream().max(byDate).orElseThrow(), "date"));
        }
        ObjectNode result = JsonNodeFactory.instance.objectNode(); result.put("type", "FeatureCollection");
        result.put("cell_size_m", source.path("cell_size_m").asInt()); result.put("feature_count", features.size()); result.set("features", features); return result;
    }
}
