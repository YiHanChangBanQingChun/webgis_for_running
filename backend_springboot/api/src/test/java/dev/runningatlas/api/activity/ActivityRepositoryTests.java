package dev.runningatlas.api.activity;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import dev.runningatlas.api.config.RunningWebgisProperties;
import tools.jackson.databind.ObjectMapper;

/** Repository tests use temporary fixtures, so they never depend on or modify personal running data. */
class ActivityRepositoryTests {

    @TempDir
    Path temporaryDataDirectory;

    @Test
    void reloadsJsonAfterDerivedFileChanges() throws Exception {
        Path activities = temporaryDataDirectory.resolve("activities.json");
        Files.writeString(activities, "[{\"id\":\"first\"}]");
        ActivityRepository repository = new ActivityRepository(
                new RunningWebgisProperties(temporaryDataDirectory.toString(), List.of()), new ObjectMapper());

        assertThat(repository.activities()).hasSize(1);

        // Changing both content and size must invalidate the repository's metadata cache.
        Files.writeString(activities, "[{\"id\":\"first\"},{\"id\":\"second\"}]");
        assertThat(repository.activities()).hasSize(2);
    }
}
