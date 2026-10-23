package dev.runningatlas.api;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

/** 启动完整 Spring 上下文，验证组件扫描、配置绑定及依赖注入能够完成。 */
@SpringBootTest
class RunningWebgisApiApplicationTests {

    @Test
    // 方法体无需断言：上下文初始化失败时，测试框架会直接报告失败。
    void contextLoads() {}
}
