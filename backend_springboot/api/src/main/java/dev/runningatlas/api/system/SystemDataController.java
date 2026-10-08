package dev.runningatlas.api.system;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import dev.runningatlas.api.activity.ActivityRepository;
import dev.runningatlas.api.common.DataReadinessService;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.JsonNodeFactory;
import tools.jackson.databind.node.ObjectNode;

/** Quality, readiness and athlete-profile endpoints. */
@RestController
@RequestMapping("/api")
public class SystemDataController {
    private final ActivityRepository repository;
    private final DataReadinessService readiness;

    public SystemDataController(ActivityRepository repository, DataReadinessService readiness) {
        this.repository = repository;
        this.readiness = readiness;
    }

    @GetMapping("/health")
    public ResponseEntity<JsonNode> health() {
        ObjectNode state = readiness.readiness();
        boolean ready = state.path("api_ready").asBoolean(false);
        ObjectNode body = JsonNodeFactory.instance.objectNode();
        body.put("status", ready ? "ok" : "not_ready"); body.set("readiness", state);
        return ResponseEntity.status(ready ? HttpStatus.OK : HttpStatus.SERVICE_UNAVAILABLE).body(body);
    }

    @GetMapping("/quality-report") public JsonNode qualityReport() { return repository.qualityReport(); }
    @GetMapping("/athlete-profile") public JsonNode athleteProfile() { return repository.athleteProfile(); }
}
