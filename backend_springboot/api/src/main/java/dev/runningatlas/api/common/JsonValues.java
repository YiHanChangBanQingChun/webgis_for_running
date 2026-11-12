package dev.runningatlas.api.common;

import tools.jackson.databind.JsonNode;

/**
 * 派生 JSON 的空值安全读取工具。
 *
 * <p>缺失值或 JSON null 的处理因用途而异：求和可使用 0，统计有效样本时应保留 null。 工具类只有静态方法，私有构造器阻止无意义的实例化。
 */
public final class JsonValues {
    /** 工具类不保存实例状态，禁止调用方创建实例。 */
    private JsonValues() {}

    /**
     * 读取文本字段，缺失或 JSON null 时返回 Java null。
     *
     * @param node 待读取或写入的 JSON 节点
     * @param field 待读取或写入的 JSON 字段名
     * @return 字段文本；缺失或 JSON null 时返回 null
     */
    public static String text(JsonNode node, String field) {
        JsonNode value = node.path(field);
        return value.isMissingNode() || value.isNull() ? null : value.asText();
    }

    /**
     * 读取数值字段，缺失或非数值时返回 0，适合求和场景。
     *
     * @param node 待读取或写入的 JSON 节点
     * @param field 待读取或写入的 JSON 字段名
     * @return 数值字段的 double 值；缺失、null 或非数值时为 0
     */
    public static double number(JsonNode node, String field) {
        JsonNode value = node.path(field);
        return value.isNumber() ? value.asDouble() : 0.0;
    }

    /**
     * 读取可空数值；无有效数值时保留 null，避免将缺失样本视为 0。
     *
     * @param node 待读取或写入的 JSON 节点
     * @return 节点的 Double 值；缺失、null 或非数值时为 null
     */
    public static Double nullableNumber(JsonNode node) {
        return node != null && node.isNumber() ? node.asDouble() : null;
    }

    /**
     * 按指定位数四舍五入；统计服务默认保留两位小数。
     *
     * @param value 待转换、舍入或校验的值
     * @param digits 保留的小数位数
     * @return 按约定位数舍入后的数值
     */
    public static double round(double value, int digits) {
        double factor = Math.pow(10, digits);
        return Math.round(value * factor) / factor;
    }
}
