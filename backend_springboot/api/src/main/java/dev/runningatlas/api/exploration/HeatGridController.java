package dev.runningatlas.api.exploration;

import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import tools.jackson.databind.JsonNode;

/** Spatial exploration endpoint. */
@RestController
@RequestMapping("/api/map")
public class HeatGridController {
    private final HeatGridService service;
    public HeatGridController(HeatGridService service) { this.service = service; }

    @GetMapping("/heat-grid")
    public JsonNode query(
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate start,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate end,
            @RequestParam(name = "min_visits", defaultValue = "1") int minVisits) {
        return service.query(start, end, minVisits);
    }
}
