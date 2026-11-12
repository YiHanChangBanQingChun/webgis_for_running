package dev.runningatlas.api.activity;

import static org.assertj.core.api.Assertions.assertThat;

import dev.runningatlas.api.config.RunningWebgisProperties;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import tools.jackson.databind.ObjectMapper;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

/** 使用临时目录和人工样本验证文件缓存，不依赖也不修改个人运动数据。 */
class ActivityRepositoryTests {

    @TempDir Path temporaryDataDirectory;

    @Test
    void reloadsJsonAfterDerivedFileChanges() throws Exception {
        Path activities = temporaryDataDirectory.resolve("activities.json");
        Files.writeString(activities, "[{\"id\":\"first\"}]");
        ActivityRepository repository =
                new ActivityRepository(
                        new RunningWebgisProperties(temporaryDataDirectory.toString(), List.of()),
                        new ObjectMapper());

        assertThat(repository.activities()).hasSize(1);

        // 改变文件内容与字节数，验证下一次读取会丢弃旧缓存。
        Files.writeString(activities, "[{\"id\":\"first\"},{\"id\":\"second\"}]");
        assertThat(repository.activities()).hasSize(2);
    }
}
