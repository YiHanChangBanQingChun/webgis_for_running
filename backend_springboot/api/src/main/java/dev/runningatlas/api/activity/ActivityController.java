package dev.runningatlas.api.activity;

import java.time.LocalDate;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import dev.runningatlas.api.common.ApiException;
import tools.jackson.databind.JsonNode;

/** Thin HTTP adapter for read-only activity endpoints. */
@RestController
@RequestMapping("/api")
public class ActivityController {
    private final ActivityService service;
    private final ActivityInsightsService insights;

    public ActivityController(ActivityService service, ActivityInsightsService insights) {
        this.service = service;
        this.insights = insights;
    }

    @GetMapping("/activities")
    public JsonNode list(
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate start,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate end,
            @RequestParam(required = false) String sport,
            @RequestParam(name = "has_gps", required = false) Boolean hasGps,
            @RequestParam(name = "min_distance_km", required = false) Double minKm,
            @RequestParam(name = "max_distance_km", required = false) Double maxKm,
            @RequestParam(defaultValue = "date_desc") String sort,
            @RequestParam(defaultValue = "0") int offset,
            @RequestParam(defaultValue = "100") int limit) {
        if (offset < 0 || limit < 1 || limit > 576) throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "offset 或 limit 超出允许范围。");
        if (minKm != null && minKm < 0 || maxKm != null && maxKm < 0) throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "距离不能为负数。");
        return service.list(start, end, sport, hasGps, minKm, maxKm, ActivityService.Sort.parse(sort), offset, limit);
    }

    @GetMapping("/calendar") public JsonNode calendar() { return service.calendar(); }
    @GetMapping("/activities/{id}") public JsonNode detail(@PathVariable String id) { return service.detail(id); }
    @GetMapping("/activities/{id}/track") public JsonNode track(@PathVariable String id) { return service.track(id); }
    @GetMapping("/activities/{id}/insights") public JsonNode insights(@PathVariable String id) { return insights.analyze(id); }
}
