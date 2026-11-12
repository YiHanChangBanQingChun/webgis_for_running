/**
 * 跑步 WebGIS 的只读 Spring Boot 查询后端。
 *
 * <p>按业务分包：activity 为活动与轨迹，statistics 为训练统计，exploration 为空间探索。 一次请求通常经过 Controller → Service →
 * Repository，再沿调用链返回 JSON。 common 提供跨模块能力，config 处理配置与跨域；原始 FIT 与 GIS 预处理仍由 Python 完成。
 *
 * <p>推荐先阅读 ActivityController 与 ActivityService，再阅读 ActivityRepository， 最后学习 StatisticsService 与
 * ActivityInsightsService 中的聚合算法。
 */
package dev.runningatlas.api;
